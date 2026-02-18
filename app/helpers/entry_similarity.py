# ==========================================
# app/helpers/entry_similarity.py
# Save-state: 202602171920
# Can handle loading embeddings from disk, raw similarity computations for embeddings, and deterministic mean. Other files may still use their own internal helpers rather than calling this file.
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

def safe_load_embedding(journal_id: str, data_dir: str = "data") -> np.ndarray:
    """
    Deterministically load embedding from journal dumps.
    Throws loudly if duplicates or missing.
    """
    import os, glob, json
    files = sorted(glob.glob(os.path.join(data_dir, "journals_embeddings_dump*.json")))
    if not files:
        raise RuntimeError("No embedding dump files found.")

    found = None
    for f in files:
        with open(f, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if journal_id in data:
            if found is not None:
                raise RuntimeError(f"Duplicate embedding found across dumps for {journal_id}")
            found = np.array(data[journal_id], dtype=np.float32)

    if found is None:
        raise RuntimeError(f"Embedding not found for journal_id {journal_id}")

    return found
