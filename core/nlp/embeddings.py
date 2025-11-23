"""
file: core/nlp/embeddings.py 
save-state updated 202511231610 (date and time formatted as follows: YYYYMMDDhhmm)
SentenceTransformer model loading (sync/async), snapshot folder detection, 
caching, deterministic fallback embeddings, and encryption helpers.
"""
from __future__ import annotations
import asyncio
import concurrent.futures
import os
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import numpy as np
from sentence_transformers import SentenceTransformer
from functools import lru_cache
from dotenv import load_dotenv
from cryptography.fernet import Fernet
import logging
import hashlib

# ---------------- Basic logging / diagnostics ----------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("peridocs.embeddings")

# ---------------- ENV SETUP ----------------
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

AES_KEY = os.environ.get("PERIDOCS_AES_KEY")
if not AES_KEY:
    raise RuntimeError("PERIDOCS_AES_KEY env variable not set")
fernet = Fernet(AES_KEY)

# ---------------- concurrency + caching ----------------
_model_lock = asyncio.Lock()
_model: Optional[SentenceTransformer] = None
_executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)
_embedding_cache: Dict[str, np.ndarray] = {}
_embedding_dim: Optional[int] = None  # determined once model is available
_deterministic_fallback_cache: Dict[str, np.ndarray] = {}

# ---------------- CONFIG ----------------
# Folder under PROJECT_ROOT/models expected to contain model snapshot folders
ROBERTA_BASE = Path(PROJECT_ROOT) / "models" / "roberta-large"


# ---------------- Model folder detection & validation ----------------
def _find_snapshot_folder(base_path: Path) -> Path:
    """
    Given base_path (e.g. models/roberta-large), find the precise snapshot folder:
    We expect exactly one snapshot folder under a nested 'models--sentence-transformers--*' path.
    Returns the path that directly contains config.json and model files.
    Raises RuntimeError if detection fails or ambiguous.
    """
    if not base_path.exists() or not base_path.is_dir():
        raise RuntimeError(f"Base model directory does not exist: {base_path}")

    # search for snapshot directories that contain 'config.json' and 'model.safetensors' or 'pytorch_model.bin'
    snapshot_candidates: List[Path] = []
    for root, dirs, files in os.walk(base_path):
        root_path = Path(root)
        # skip hidden directories early
        if any(part.startswith(".") for part in root_path.parts):
            continue
        if "config.json" in files and (
            "model.safetensors" in files or "pytorch_model.bin" in files or "modules.json" in files
        ):
            snapshot_candidates.append(root_path)

    if not snapshot_candidates:
        raise RuntimeError(f"No valid model snapshot folder found under {base_path}. Looked for config.json + model file.")
    # you told me there is exactly one snapshot — enforce it
    if len(snapshot_candidates) > 1:
        # pick the candidate with the largest filesize total as a heuristic (but still error to force explicitness)
        sizes: List[Tuple[int, Path]] = []
        for p in snapshot_candidates:
            total = 0
            for f in p.rglob("*"):
                if f.is_file():
                    try:
                        total += f.stat().st_size
                    except Exception:
                        pass
            sizes.append((total, p))
        sizes.sort(reverse=True)
        # if top candidate is significantly larger, choose it but warn
        best_size, best_path = sizes[0]
        second_size = sizes[1][0] if len(sizes) > 1 else 0
        if best_size > second_size * 1.2:
            logger.warning("Multiple snapshot folders found, selecting largest one (%s).", best_path)
            return best_path
        raise RuntimeError(
            f"Multiple valid snapshot folders found under {base_path}. Candidates: {snapshot_candidates}. "
            "Please ensure exactly one snapshot folder exists."
        )

    return snapshot_candidates[0]


def validate_model_folder(base_path: Optional[Path] = None) -> Path:
    """
    Public validator to confirm model folder is usable.
    Returns the resolved snapshot folder Path on success; raises RuntimeError on failure.
    """
    base = base_path or ROBERTA_BASE
    folder = _find_snapshot_folder(base)
    # quick sanity checks
    if not (folder / "config.json").exists():
        raise RuntimeError(f"Invalid model folder (missing config.json): {folder}")
    if not ((folder / "model.safetensors").exists() or (folder / "pytorch_model.bin").exists()):
        raise RuntimeError(f"Invalid model folder (missing model file): {folder}")
    # require tokenizer files too
    if not (folder / "tokenizer.json").exists() and not (folder / "vocab.json").exists():
        raise RuntimeError(f"Invalid model folder (missing tokenizer files): {folder}")
    logger.info("Model folder validated: %s", folder)
    return folder


# ---------------- MODEL LOADING ----------------
def _set_embedding_dim_from_model(model: SentenceTransformer):
    global _embedding_dim
    if _embedding_dim is None:
        # do a single encode to discover dim
        try:
            dummy = model.encode("test", convert_to_numpy=True, normalize_embeddings=False)
            if dummy is None or getattr(dummy, "shape", None) is None:
                raise RuntimeError("Unable to determine embedding dimension from model.encode()")
            _embedding_dim = int(dummy.shape[0])
            logger.info("Detected embedding dimension: %s", _embedding_dim)
        except Exception as e:
            raise RuntimeError(f"Failed to set embedding dim: {e}")


def load_model() -> SentenceTransformer:
    """
    Synchronous loader (blocking). Uses snapshot detection and sets _model singleton.
    Guarantees _embedding_dim is set on success.
    """
    global _model
    if _model is not None:
        return _model

    folder = validate_model_folder(ROBERTA_BASE)
    logger.info("Loading SentenceTransformer model from: %s", folder)
    model = SentenceTransformer(str(folder))
    _set_embedding_dim_from_model(model)
    _model = model
    return _model


async def _load_model() -> SentenceTransformer:
    """
    Async loader for SentenceTransformer with singleton pattern.
    Safe to call multiple times.
    """
    global _model
    async with _model_lock:
        if _model is not None:
            return _model
        folder = validate_model_folder(ROBERTA_BASE)
        logger.info("Async loading SentenceTransformer model from: %s", folder)
        loop = asyncio.get_running_loop()
        model = await loop.run_in_executor(_executor, lambda: SentenceTransformer(str(folder)))
        _set_embedding_dim_from_model(model)
        _model = model
        return _model


def get_model() -> SentenceTransformer:
    """Synchronous getter for the preloaded model (raises if not loaded)."""
    if _model is None:
        raise RuntimeError("Model not loaded yet. Call load_model() or await _load_model().")
    return _model


# ---------------- EMBEDDING COMPUTATION ----------------
@lru_cache(maxsize=4096)
def _embed_sync(text: str) -> np.ndarray:
    """
    Compute embedding synchronously using preloaded or auto-loaded model.
    This function is run in a thread-pool to avoid blocking event loop.
    """
    # ensure model is loaded in the calling thread (synchronous)
    model = _model or load_model()
    arr = model.encode(text, convert_to_numpy=True, normalize_embeddings=True)
    if arr is None:
        raise RuntimeError("SentenceTransformer returned None embedding")
    return np.asarray(arr, dtype=np.float32)


async def batch_embeddings_async(
    texts: list[str], batch_size: int = 8, allow_fallback: bool = False
) -> np.ndarray:
    """
    Async batch embedding computation with caching and auto-folder detection.
    Returns np.ndarray of shape (len(texts), embed_dim) or raises.
    If model is missing and allow_fallback is True, deterministic fallback vectors will be returned.
    """
    # quick empty case
    if not texts:
        if _embedding_dim is None:
            # if dimension unknown, fallback to common size 768 as safe default
            dim = 768
        else:
            dim = _embedding_dim
        return np.zeros((0, dim), dtype=np.float32)

    # ensure model is loaded
    try:
        await _load_model()
    except Exception as e:
        logger.exception("Model load failed in batch_embeddings_async: %s", e)
        if not allow_fallback:
            raise
        logger.warning("Using deterministic fallback embeddings due to model load failure.")
        return np.stack([_deterministic_fallback_vec(t) for t in texts])

    results: list[np.ndarray] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        batch_tasks: list[asyncio.Future] = []
        for text in batch:
            if not text or not text.strip():
                batch_tasks.append(asyncio.get_running_loop().create_future())
                batch_tasks[-1].set_result(np.zeros((_embedding_dim,), dtype=np.float32))
            elif text in _embedding_cache:
                fut = asyncio.get_running_loop().create_future()
                fut.set_result(_embedding_cache[text])
                batch_tasks.append(fut)
            else:
                fut = asyncio.get_running_loop().run_in_executor(_executor, _embed_sync, text)
                batch_tasks.append(fut)

        batch_results = await asyncio.gather(*batch_tasks)
        for text, emb in zip(batch, batch_results):
            # cache but defensive copy
            arr = np.asarray(emb, dtype=np.float32)
            if arr.size == 0:
                logger.warning("Received empty embedding for text: %s", text[:80])
                if _embedding_dim is None:
                    # when dimension unknown, force a safe default
                    arr = np.zeros((768,), dtype=np.float32)
                else:
                    arr = np.zeros((_embedding_dim,), dtype=np.float32)
            _embedding_cache[text] = arr
            results.append(arr)

    return np.stack(results)


async def get_embedding_async(text: str, allow_fallback: bool = False) -> np.ndarray:
    """
    Async wrapper for a single text embedding. Returns deterministic fallback vector
    if allow_fallback == True and model cannot be loaded.
    """
    if _embedding_dim is None and _model is None:
        # try to set dimension by loading model; if this fails we may fallback
        try:
            await _load_model()
        except Exception as e:
            logger.debug("Model load failed in get_embedding_async: %s", e)
            if not allow_fallback:
                raise
            logger.warning("Using deterministic fallback embedding (allow_fallback=True).")

    if not text or not text.strip():
        if _embedding_dim is None:
            dim = 768
        else:
            dim = _embedding_dim
        return np.zeros((dim,), dtype=np.float32)

    if text in _embedding_cache:
        return _embedding_cache[text]

    try:
        emb = (await batch_embeddings_async([text], allow_fallback=allow_fallback))[0]
        _embedding_cache[text] = emb
        return emb
    except Exception as e:
        logger.exception("get_embedding_async failed: %s", e)
        if allow_fallback:
            return _deterministic_fallback_vec(text)
        raise

def get_embedding(text: str, allow_fallback: bool = False) -> np.ndarray:
    """
    Synchronous wrapper for get_embedding_async.
    Safe inside a running asyncio loop by using synchronous _embed_sync.
    """
    if not text or not text.strip():
        dim = _embedding_dim or 768
        return np.zeros((dim,), dtype=np.float32)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No running loop — safe to run async directly
        return asyncio.run(get_embedding_async(text, allow_fallback=allow_fallback))

    if loop.is_running():
        # Running inside an event loop — avoid fut.result() deadlock
        try:
            model = _model or load_model()
            return _embed_sync(text)
        except Exception as e:
            logger.exception("Synchronous get_embedding failed inside running loop: %s", e)
            if allow_fallback:
                return _deterministic_fallback_vec(text)
            raise
    else:
        return asyncio.run(get_embedding_async(text, allow_fallback=allow_fallback))

def batch_embeddings(texts: list[str], batch_size: int = 8, allow_fallback: bool = False) -> np.ndarray:
    """
    Synchronous wrapper for batch_embeddings_async.
    Safe inside a running asyncio loop by using synchronous _embed_sync per text.
    """
    if not texts:
        dim = _embedding_dim or 768
        return np.zeros((0, dim), dtype=np.float32)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(batch_embeddings_async(texts, batch_size=batch_size, allow_fallback=allow_fallback))

    if loop.is_running():
        try:
            model = _model or load_model()
            return np.stack([_embed_sync(t) for t in texts])
        except Exception as e:
            logger.exception("Synchronous batch_embeddings failed inside running loop: %s", e)
            if allow_fallback:
                return np.stack([_deterministic_fallback_vec(t) for t in texts])
            raise
    else:
        return asyncio.run(batch_embeddings_async(texts, batch_size=batch_size, allow_fallback=allow_fallback))


# ---------------- Deterministic fallback (dev only) ----------------
def _deterministic_fallback_vec(text: str) -> np.ndarray:
    if text in _deterministic_fallback_cache:
        return _deterministic_fallback_cache[text]
    dim = _embedding_dim or 768
    h = hashlib.sha256(text.encode("utf-8")).digest()
    rng = np.frombuffer(h * ((dim // len(h)) + 1), dtype=np.uint8)[:dim].astype(np.float32)
    rng = rng - np.mean(rng)
    norm = np.linalg.norm(rng)
    if norm == 0:
        rng = np.ones((dim,), dtype=np.float32)
        norm = float(np.linalg.norm(rng))
    vec = (rng / norm).astype(np.float32)
    _deterministic_fallback_cache[text] = vec
    return vec


# ---------------- Entry-level helper ----------------
async def embed_entry_text(raw_text: str, pii_protected_text: str, allow_fallback: bool = False) -> np.ndarray:
    """Compute embedding for a single entry; returns vector only."""
    return await get_embedding_async(raw_text, allow_fallback=allow_fallback)


# ---------------- Encryption helpers ----------------
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


# ---------------- Legacy / debug helpers ----------------
TOKEN_EMBED_PRECOMPUTE: dict[str, np.ndarray] = {}

def model_status() -> Dict[str, Optional[int]]:
    """Return small status useful for diagnostics: whether model loaded and embedding dim."""
    return {"loaded": _model is not None, "embedding_dim": _embedding_dim}

