# file: core/nlp/embeddings.py
"""
Embeddings module for PeriDocs NLP pipeline.

Provides:
- Async and sync embedding generation using all-roberta-large-v1.
- Automatic nested folder detection under models/roberta-large.
- Offline caching with singleton pattern.
- Safe handling of empty or whitespace-only inputs.
- Batch embeddings with consistent caching logic.
- Optional encryption for sensitive text.
- Legacy precompute dict for backward compatibility.

Functions:
- get_embedding_async(text) -> np.ndarray
- batch_embeddings_async(texts) -> np.ndarray
- get_embedding(text) -> np.ndarray (sync)
- batch_embeddings(texts) -> np.ndarray (sync)
- embed_entry_text(raw_text, pii_protected_text) -> np.ndarray
- encrypt_text(text) / decrypt_text(ciphertext)

Regarding the size of this file:
-All functionality is tightly interdependent (cache, sync/async, batch, single, model path).
-Splitting would add multiple small files that all need to be imported just to get embeddings — potentially overkill for this size.
-If the file grows beyond ~300 lines or you add multiple model types, splitting would make sense.
# file: core/nlp/embeddings.py
"""

from __future__ import annotations
import asyncio
import concurrent.futures
import os
from pathlib import Path
from typing import List, Dict, Optional
import numpy as np
from sentence_transformers import SentenceTransformer
from functools import lru_cache
from dotenv import load_dotenv
from cryptography.fernet import Fernet

# ---------------- ENV SETUP ----------------
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

AES_KEY = os.environ.get("PERIDOCS_AES_KEY")
if not AES_KEY:
    raise RuntimeError("PERIDOCS_AES_KEY env variable not set")
fernet = Fernet(AES_KEY)

# ---------------- MODEL PRELOAD & AUTO-FOLDER DETECTION ----------------
_model_lock = asyncio.Lock()
_model: Optional[SentenceTransformer] = None
_executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)
_embedding_cache: Dict[str, np.ndarray] = {}
_embedding_dim: Optional[int] = None  # NEW: dynamically track embedding dimension

def _detect_model_folder(base_path: Path) -> Path:
    """
    Recursively detect the folder containing a SentenceTransformer model.
    
    Args:
        base_path (Path): Base directory for the model (e.g., models/roberta-large)
    
    Returns:
        Path: Path to the folder containing a model (with config.json)
    
    Raises:
        RuntimeError: If no valid model folder is found
    """
    if not base_path.exists() or not base_path.is_dir():
        raise RuntimeError(f"Base model directory does not exist: {base_path}")

    # Walk recursively
    for root, dirs, files in os.walk(base_path):
        root_path = Path(root)

        # Skip hidden folders
        dirs[:] = [d for d in dirs if not d.startswith(".")]

        if "config.json" in files:
            return root_path

    raise RuntimeError(f"No valid SentenceTransformer model folder found under: {base_path}")


def _set_embedding_dim(model: SentenceTransformer):
    """Set the global embedding dimension based on the model output."""
    global _embedding_dim
    if _embedding_dim is None:
        dummy = model.encode("test", convert_to_numpy=True, normalize_embeddings=True)
        _embedding_dim = dummy.shape[0]
        if _embedding_dim is None:
            raise RuntimeError("Failed to detect embedding dimension from model.")


# Ensure offline mode to avoid any network requests / telemetry
os.environ["TRANSFORMERS_OFFLINE"] = "1"

def load_model() -> SentenceTransformer:
    """Synchronously load the SentenceTransformer model using auto-folder detection."""
    global _model
    if _model is None:
        roberta_base = Path(PROJECT_ROOT) / "models" / "roberta-large"
        model_path = _detect_model_folder(roberta_base)
        _model = SentenceTransformer(str(model_path))  # offline-safe instantiation
        _set_embedding_dim(_model)  # set embedding dimension after loading
    return _model


async def _load_model() -> SentenceTransformer:
    """
    Async loader for SentenceTransformer with singleton pattern.
    Safe to call multiple times. Detects nested folder automatically.
    """
    global _model
    async with _model_lock:
        if _model is not None:
            return _model

        base_dir = Path(PROJECT_ROOT) / "models" / "roberta-large"
        model_path = _detect_model_folder(base_dir)

        loop = asyncio.get_running_loop()
        _model = await loop.run_in_executor(
            _executor,
            lambda: SentenceTransformer(str(model_path))  # offline-safe instantiation
        )
        _set_embedding_dim(_model)  # set embedding dimension after loading
        return _model
        
def get_model() -> SentenceTransformer:
    """Synchronous getter for the preloaded model (raises if not loaded)."""
    if _model is None:
        raise RuntimeError("Model not loaded yet. Call _load_model() first.")
    return _model

# ---------------- EMBEDDING COMPUTATION ----------------
@lru_cache(maxsize=4096)
def _embed_sync(text: str) -> np.ndarray:
    """Compute embedding synchronously using the preloaded or auto-loaded model."""
    model = _model or load_model()
    return model.encode(text, convert_to_numpy=True, normalize_embeddings=True)


async def batch_embeddings_async(
    texts: list[str], batch_size: int = 8
) -> np.ndarray:
    """Async batch embedding computation with caching and auto-folder detection."""
    if not texts:
        return np.zeros((0, _embedding_dim), dtype=np.float32)

    await _load_model()
    results: list[np.ndarray] = []

    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        batch_tasks: list[asyncio.Future] = []

        for text in batch:
            if not text or not text.strip():
                fut = asyncio.Future()
                fut.set_result(np.zeros((_embedding_dim,), dtype=np.float32))
                batch_tasks.append(fut)
            elif text in _embedding_cache:
                fut = asyncio.Future()
                fut.set_result(_embedding_cache[text])
                batch_tasks.append(fut)
            else:
                loop = asyncio.get_running_loop()
                fut = loop.run_in_executor(_executor, _embed_sync, text)
                batch_tasks.append(fut)

        batch_results = await asyncio.gather(*batch_tasks)
        for text, emb in zip(batch, batch_results):
            _embedding_cache[text] = emb
            results.append(emb)

    return np.stack(results)


async def get_embedding_async(text: str) -> np.ndarray:
    """
    Async wrapper for a single text embedding.
    Leverages batch_embeddings_async for consistent caching.
    Returns zero vector for empty or whitespace-only text.
    """
    if not text or not text.strip():
        return np.zeros((_embedding_dim,), dtype=np.float32)

    if text in _embedding_cache:
        return _embedding_cache[text]

    emb = (await batch_embeddings_async([text]))[0]
    _embedding_cache[text] = emb
    return emb


def get_embedding(text: str) -> np.ndarray:
    """Synchronous wrapper for get_embedding_async."""
    if not text or not text.strip():
        return np.zeros((_embedding_dim,), dtype=np.float32)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(get_embedding_async(text))

    if loop.is_running():
        return asyncio.run_coroutine_threadsafe(get_embedding_async(text), loop).result()
    else:
        return asyncio.run(get_embedding_async(text))


def batch_embeddings(texts: list[str], batch_size: int = 8) -> np.ndarray:
    """Synchronous wrapper for batch_embeddings_async."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(batch_embeddings_async(texts, batch_size=batch_size))

    if loop.is_running():
        return asyncio.run_coroutine_threadsafe(
            batch_embeddings_async(texts, batch_size=batch_size), loop
        ).result()
    else:
        return asyncio.run(batch_embeddings_async(texts, batch_size=batch_size))


# ---------------- ENTRY-LEVEL HELPER ----------------
async def embed_entry_text(raw_text: str, pii_protected_text: str) -> np.ndarray:
    """Compute embedding for a single entry; returns vector only."""
    return await get_embedding_async(raw_text)


# ---------------- ENCRYPTION HELPERS ----------------
def encrypt_text(text: str) -> str:
    if not text:
        return text
    token = fernet.encrypt(text.encode("utf-8"))
    return token.decode("utf-8")


def decrypt_text(ciphertext: str) -> str:
    if not ciphertext:
        return ciphertext
    plain = fernet.decrypt(ciphertext.encode("utf-8"))
    return plain.decode("utf-8")


# ---------------- LEGACY COMPATIBILITY ----------------
TOKEN_EMBED_PRECOMPUTE: dict[str, np.ndarray] = {}
