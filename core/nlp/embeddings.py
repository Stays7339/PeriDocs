# ==========================================
# core/nlp/embeddings.py
# save-state updated 202512151237
# ==========================================
from __future__ import annotations
import asyncio
from pathlib import Path
from typing import List
import numpy as np
from sentence_transformers import SentenceTransformer
from cryptography.fernet import Fernet
import os
from dotenv import load_dotenv
import hashlib
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
_model: SentenceTransformer = None
_executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)
_embedding_cache = {}
_embedding_dim: int = None

TOKEN_EMBED_PRECOMPUTE = True  # Global flag

async def get_embedding_async(text: str) -> np.ndarray:
    if not text.strip():
        raise ValueError("Cannot compute embedding for empty text")
    if TOKEN_EMBED_PRECOMPUTE and text in _embedding_cache:
        return _embedding_cache[text]
    model = await _load_model()
    loop = asyncio.get_running_loop()
    emb = await loop.run_in_executor(_executor, lambda: model.encode(text, convert_to_numpy=True))
    if emb is None or not isinstance(emb, np.ndarray):
        raise RuntimeError("Embedding computation failed: got None or invalid type")
    norm = np.linalg.norm(emb)
    if norm > 0:
        emb = emb / norm
    if TOKEN_EMBED_PRECOMPUTE:
        _embedding_cache[text] = emb
    return emb


ROBERTA_BASE = Path(PROJECT_ROOT) / "models" / "roberta-large"

# ---------------- Model validation ----------------
def _find_snapshot_folder(base_path: Path) -> Path:
    if not base_path.exists() or not base_path.is_dir():
        raise RuntimeError(f"Base model directory does not exist: {base_path}")

    snapshot_candidates = []
    for root, dirs, files in os.walk(base_path):
        root_path = Path(root)
        if any(part.startswith(".") for part in root_path.parts):
            continue
        if "config.json" in files and ("model.safetensors" in files or "pytorch_model.bin" in files):
            snapshot_candidates.append(root_path)

    if not snapshot_candidates:
        raise RuntimeError(f"No valid model snapshot folder found under {base_path}")

    return snapshot_candidates[0]

def validate_model_folder(base_path: Path = None) -> Path:
    base = base_path or ROBERTA_BASE
    folder = _find_snapshot_folder(base)
    if not (folder / "config.json").exists():
        raise RuntimeError(f"Invalid model folder (missing config.json): {folder}")
    if not ((folder / "model.safetensors").exists() or (folder / "pytorch_model.bin").exists()):
        raise RuntimeError(f"Invalid model folder (missing model file): {folder}")
    return folder

# ---------------- Encryption ----------------
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

# ---------------- Embedding ----------------
async def _load_model() -> SentenceTransformer:
    global _model
    async with _model_lock:
        if _model is None:
            folder = validate_model_folder()
            _model = SentenceTransformer(str(folder))
            logger.info(f"Loaded SentenceTransformer from {folder}")
    return _model

async def get_embedding_async(text: str) -> np.ndarray:
    if not text.strip():
        raise ValueError("Cannot compute embedding for empty text")
    model = await _load_model()
    loop = asyncio.get_running_loop()
    emb = await loop.run_in_executor(_executor, lambda: model.encode(text, convert_to_numpy=True))
    if emb is None or not isinstance(emb, np.ndarray):
        raise RuntimeError("Embedding computation failed: got None or invalid type")
    norm = np.linalg.norm(emb)
    if norm > 0:
        emb = emb / norm
    return emb

def model_status() -> dict:
    return {
        "loaded": _model is not None,
        "embedding_dim": _embedding_dim if _embedding_dim else 0,
        "cache_size": len(_embedding_cache)
    }
