# ==========================================
# core/nlp/embeddings.py
# save-state updated 2026-03-18T13:13:00-04:00
# ------------------------------------------

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import os
from pathlib import Path

import numpy as np
from cryptography.fernet import Fernet
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer

# ---------------- Logging ----------------
logger = logging.getLogger("peridocs.embeddings")

# ---------------- Paths / Environment ----------------
PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

AES_KEY = os.environ.get("PERIDOCS_AES_KEY")
if not AES_KEY:
    raise RuntimeError("PERIDOCS_AES_KEY env variable not set")

fernet = Fernet(AES_KEY)

# ---------------- Hugging Face / Model Configuration ----------------
MODEL_NAME = "sentence-transformers/all-roberta-large-v1"
MODEL_REVISION = "cf74d8acd4f198de950bf004b262e6accfed5d2c"

MODEL_CACHE_DIR = PROJECT_ROOT / "models"
ROBERTA_SNAPSHOT_DIR = (
    MODEL_CACHE_DIR
    / "models--sentence-transformers--all-roberta-large-v1"
    / "snapshots"
    / MODEL_REVISION
)

# Explicitly disable HF telemetry
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"

# Force local-only execution behavior in runtime environment
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_DATASETS_OFFLINE", "1")

# ---------------- Model / Concurrency ----------------
_model_lock = asyncio.Lock()
_model: SentenceTransformer | None = None
_executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)
_embedding_cache: dict[str, np.ndarray] = {}

TOKEN_EMBED_PRECOMPUTE = True


# ==========================================================
# Internal Validation Helpers
# ==========================================================

def _validate_snapshot_dir(snapshot_dir: Path) -> None:
    """
    Validate that the pinned local SentenceTransformer snapshot exists and
    contains the minimum required files for loading.

    Fails loudly with precise diagnostics if the model directory is missing
    or malformed.
    """
    if not snapshot_dir.exists():
        raise RuntimeError(
            f"Model snapshot directory does not exist: {snapshot_dir}"
        )

    if not snapshot_dir.is_dir():
        raise RuntimeError(
            f"Model snapshot path exists but is not a directory: {snapshot_dir}"
        )

    required_files = [
        "config.json",
    ]

    optional_weight_files = [
        "model.safetensors",
        "pytorch_model.bin",
    ]

    missing_required = [
        fname for fname in required_files if not (snapshot_dir / fname).exists()
    ]
    if missing_required:
        raise RuntimeError(
            "Model snapshot directory is missing required files "
            f"{missing_required}: {snapshot_dir}"
        )

    if not any((snapshot_dir / fname).exists() for fname in optional_weight_files):
        raise RuntimeError(
            "Model snapshot directory is missing model weights "
            f"({optional_weight_files}): {snapshot_dir}"
        )


def _encode_single_text(model: SentenceTransformer, text: str) -> np.ndarray:
    """
    Synchronous worker function for executor-backed single-text embedding.
    """
    emb = model.encode(
        text,
        convert_to_numpy=True,
    )

    if not isinstance(emb, np.ndarray):
        raise RuntimeError("Embedding computation failed: expected numpy.ndarray")

    return emb


# ==========================================================
# Model Loading
# ==========================================================

async def _load_model() -> SentenceTransformer:
    """
    Lazily load the pinned SentenceTransformer model exactly once.

    Uses an asyncio lock to ensure only one load occurs during concurrent
    startup or request handling.
    """
    global _model

    async with _model_lock:
        if _model is not None:
            return _model

        _validate_snapshot_dir(ROBERTA_SNAPSHOT_DIR)

        try:
            _model = SentenceTransformer(
                str(ROBERTA_SNAPSHOT_DIR),
                local_files_only=True,
            )
        except Exception as e:
            raise RuntimeError(
                "Failed to load pinned local SentenceTransformer snapshot "
                f"from {ROBERTA_SNAPSHOT_DIR}: {e}"
            ) from e

        logger.info("Loaded SentenceTransformer from %s", ROBERTA_SNAPSHOT_DIR)
        return _model


# ==========================================================
# Embedding
# ==========================================================

async def get_embedding_async(
    text_or_texts: str | list[str],
    entry_id: str | None = None,
) -> np.ndarray | list[np.ndarray]:
    """
    Compute embedding(s) for a single string or a list of strings.

    Behavior:
    - If input is a single string, returns np.ndarray
    - If input is a list[str], returns list[np.ndarray]
    - Does NOT normalize embeddings
    - Uses in-memory caching if TOKEN_EMBED_PRECOMPUTE is enabled

    Parameters:
    - text_or_texts: input text or list of texts
    - entry_id: optional identifier reserved for downstream logging/audit hooks
    """
    del entry_id  # retained for interface stability / future logging hooks

    if isinstance(text_or_texts, str):
        texts = [text_or_texts]
        single_input = True
    elif isinstance(text_or_texts, list):
        if not text_or_texts:
            raise ValueError("Cannot compute embedding for empty list")
        if not all(isinstance(t, str) for t in text_or_texts):
            raise TypeError("All items in input list must be strings")
        texts = text_or_texts
        single_input = False
    else:
        raise TypeError("Input must be a string or list of strings")

    model = await _load_model()
    loop = asyncio.get_running_loop()

    results: list[np.ndarray] = []

    for text in texts:
        if not text.strip():
            raise ValueError("Cannot compute embedding for empty string")

        if TOKEN_EMBED_PRECOMPUTE and text in _embedding_cache:
            results.append(_embedding_cache[text])
            continue

        emb = await loop.run_in_executor(
            _executor,
            _encode_single_text,
            model,
            text,
        )

        if TOKEN_EMBED_PRECOMPUTE:
            _embedding_cache[text] = emb

        results.append(emb)

    return results[0] if single_input else results


# ==========================================================
# Encryption
# ==========================================================

def encrypt_text(text: str) -> str:
    """
    Encrypt plaintext using the configured Fernet key.
    Returns the original value unchanged if empty.
    """
    if not text:
        return text
    return fernet.encrypt(text.encode("utf-8")).decode("utf-8")


def decrypt_text(ciphertext: str) -> str:
    """
    Decrypt ciphertext using the configured Fernet key.
    Returns the original value unchanged if empty.
    """
    if not ciphertext:
        return ciphertext
    return fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")