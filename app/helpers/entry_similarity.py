# ==========================================
# app/helpers/entry_similarity.py
# Save-state: 202602201320
# Can handle loading embeddings from disk, raw similarity computations for embeddings, 
# and deterministic mean. Other files may still use their own internal helpers rather than calling this file.
# ==========================================
import os
import numpy as np
from typing import Optional, Sequence
import logging

logger = logging.getLogger("peridocs.entry_similarity")

DATA_DIR = os.getenv("PERIDOCS_DATA_DIR", "data")

def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """
    Compute cosine similarity between two vectors.
    
    Raises:
        ValueError: if either input vector has zero norm.
    
    Logs a warning with context before raising.
    """
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)

    if norm_a == 0 or norm_b == 0:
        logger.warning(
            "Attempted cosine similarity with zero vector: "
            "norm_a=%f, norm_b=%f, vector_a=%s, vector_b=%s",
            norm_a, norm_b,
            np.array2string(a, precision=3, edgeitems=5),
            np.array2string(b, precision=3, edgeitems=5),
        )
        raise ValueError("Cannot compute cosine similarity with zero vector")

    return float(np.dot(a, b) / (norm_a * norm_b))

def deterministic_mean(vectors: Sequence[np.ndarray]) -> np.ndarray:
    if not vectors:
        raise ValueError("Empty vector list")
    stacked = np.stack(vectors)
    return stacked.mean(axis=0)

def safe_load_embedding(entry_id: str, data_dir: str = "data") -> np.ndarray:
    """
    Deterministically load embedding from entry dumps.
    Supports .npz format (preferred) and falls back to JSON for legacy files.
    Throws loudly if duplicates or missing.
    """
    import os, glob, json
    npz_files = sorted(glob.glob(os.path.join(data_dir, "entries_embeddings_dump*.npz")))
    json_files = sorted(glob.glob(os.path.join(data_dir, "entries_embeddings_dump*.json")))

    found = None

    # --- Try NPZ first ---
    for f in npz_files:
        with np.load(f, allow_pickle=False) as data:  # <-- Pickle OFF, which is CRUCIAL for avoiding malware.
            # Only accept keys that are 8-char hex sha8
            for k in data.keys():
                if not isinstance(k, str) or len(k) != 8 or not all(c in "0123456789abcdef" for c in k.lower()):
                    raise RuntimeError(f"Unexpected key in NPZ dump: {k}")
            if entry_id in data:
                if found is not None:
                    raise RuntimeError(f"Duplicate embedding found across dumps for {entry_id}")
                found = data[entry_id].astype(np.float32)

    # --- Fallback to JSON ---
    for f in json_files:
        with open(f, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if entry_id in data:
            if found is not None:
                raise RuntimeError(f"Duplicate embedding found across dumps for {entry_id}")
            found = np.array(data[entry_id], dtype=np.float32)

    if found is None:
        raise RuntimeError(f"Embedding not found for entry_id {entry_id}")

    return found