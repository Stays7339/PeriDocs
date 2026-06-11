
# ==========================================
# app/helpers/entry_similarity.py
# Save-state: 2026-05-19T14:14:10-04:00
# Can handle loading embeddings from disk, raw similarity computations for embeddings, 
# and deterministic mean. Other files may still use their own internal helpers rather than calling this file.
# ==========================================
import os
import numpy as np
import logging
from typing import Optional, Sequence
from pathlib import Path

logger = logging.getLogger(__name__)

# Base data directory (can be overridden with environment variable)
DATA_DIR = Path(os.getenv("PERIDOCS_DATA_DIR", "data"))

# Subdirectories
ENTRIES_DIR = DATA_DIR / "entries"        


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

async def safe_load_embedding(entry_id: str, entry_runtime) -> np.ndarray:
    emb = await entry_runtime.get_embedding(entry_id)

    if emb is None:
        raise RuntimeError(f"Embedding not found in runtime for entry_id {entry_id}")

    return np.asarray(emb, dtype=np.float32)

def highlight_standout_clauses(window_embeddings: np.ndarray, threshold: float = 0.7) -> list[bool]:
    """
    Identify clauses that are 'standout' relative to other clauses in the same entry.

    Each clause is compared to the mean of all other clauses via cosine similarity.
    If similarity < threshold, it is considered standout.

    Returns a list of booleans aligned with window_embeddings.
    """
    n = len(window_embeddings)
    if n == 0:
        return []

    standout_window_flags = []
    for i in range(n):
        other_embeddings = np.delete(window_embeddings, i, axis=0)
        mean_other = window_embeddings[i] if other_embeddings.size == 0 else other_embeddings.mean(axis=0)
        sim = cosine_similarity(window_embeddings[i], mean_other)
        standout_window_flags.append(sim < threshold)

    return standout_window_flags