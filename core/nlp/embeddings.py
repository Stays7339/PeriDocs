# ==========================================
# core/nlp/embeddings.py
# save-state updated 202512171302
# ------------------------------------------

from __future__ import annotations
import asyncio
from pathlib import Path
import numpy as np
from sentence_transformers import SentenceTransformer
from cryptography.fernet import Fernet
import os
from dotenv import load_dotenv
import concurrent.futures
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("peridocs.embeddings")

# ---------------- ENV ----------------
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

AES_KEY = os.environ.get("PERIDOCS_AES_KEY")
if not AES_KEY:
    raise RuntimeError("PERIDOCS_AES_KEY env variable not set")

fernet = Fernet(AES_KEY)

# ---------------- Model / Concurrency ----------------
_model_lock = asyncio.Lock()
_model: SentenceTransformer | None = None
_executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)
_embedding_cache: dict[str, np.ndarray] = {}

TOKEN_EMBED_PRECOMPUTE = True

ROBERTA_BASE = Path(PROJECT_ROOT) / "models" / "roberta-large"

# ---------------- Model loading ----------------
async def _load_model() -> SentenceTransformer:
    global _model
    async with _model_lock:
        if _model is None:
            folder = _find_snapshot_folder(ROBERTA_BASE)
            _model = SentenceTransformer(str(folder))
            logger.info(f"Loaded SentenceTransformer from {folder}")
    return _model

def _find_snapshot_folder(base_path: Path) -> Path:
    for root, _, files in os.walk(base_path):
        if "config.json" in files and (
            "model.safetensors" in files or "pytorch_model.bin" in files
        ):
            return Path(root)
    raise RuntimeError(f"No valid model snapshot found under {base_path}")

# ---------------- Embedding ----------------
async def get_embedding_async(text_or_texts: str | list[str]) -> np.ndarray | list[np.ndarray]:
    """
    Compute embedding(s) for input text or list of texts.
    - If a single string is provided, returns np.ndarray.
    - If a list of strings is provided, returns a list of np.ndarray.
    
    Does NOT normalize; downstream code should normalize for cosine similarity, centroids, etc.
    Uses caching if TOKEN_EMBED_PRECOMPUTE=True.
    """
    if isinstance(text_or_texts, str):
        texts = [text_or_texts]
        single_input = True
    elif isinstance(text_or_texts, list):
        if not text_or_texts:
            raise ValueError("Cannot compute embedding for empty list")
        texts = text_or_texts
        single_input = False
    else:
        raise TypeError("Input must be a string or list of strings")

    model = await _load_model()
    loop = asyncio.get_running_loop()

    results: list[np.ndarray] = []

    for t in texts:
        if not t.strip():
            raise ValueError("Cannot compute embedding for empty string")
        if TOKEN_EMBED_PRECOMPUTE and t in _embedding_cache:
            results.append(_embedding_cache[t])
            continue

        emb = await loop.run_in_executor(
            _executor,
            lambda text=t: model.encode(text, convert_to_numpy=True)
        )
        if not isinstance(emb, np.ndarray):
            raise RuntimeError("Embedding computation failed")
        if TOKEN_EMBED_PRECOMPUTE:
            _embedding_cache[t] = emb
        results.append(emb)

    return results[0] if single_input else results

# ---------------- Encryption ----------------
def encrypt_text(text: str) -> str:
    if not text:
        return text
    return fernet.encrypt(text.encode("utf-8")).decode("utf-8")

def decrypt_text(ciphertext: str) -> str:
    if not ciphertext:
        return ciphertext
    return fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
