# ==========================================
# app/helpers/entry_similarity.py
# Save-state: 2026-03-15T18:56:45-05:00
# Can handle loading embeddings from disk, raw similarity computations for embeddings, 
# and deterministic mean. Other files may still use their own internal helpers rather than calling this file.
# ==========================================
import os
import numpy as np
import logging

from typing import Optional, Sequence
from pathlib import Path

logger = logging.getLogger("peridocs.entry_similarity")

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

def safe_load_embedding(entry_id: str, data_dir: str = DATA_DIR) -> np.ndarray:
    import os, glob, json
    npz_files = sorted(ENTRIES_DIR.glob("entries_mean_embeddings_dump*.npz"))
    json_files = sorted(ENTRIES_DIR.glob("entries_mean_embeddings_dump*.json"))

    found = None
    found_in_file = None

    # --- Try NPZ first ---
    for f in npz_files:
        with np.load(f, allow_pickle=False) as data:
            for k in data.keys():
                if not isinstance(k, str) or len(k) != 8 or not all(c in "0123456789abcdef" for c in k.lower()):
                    raise RuntimeError(f"Unexpected key in NPZ dump: {k}")

            if entry_id in data: 
                logger.warning(
                    "Embedding key match in NPZ file: entry_id=%s file=%s total_keys=%d",
                    entry_id, f, len(data.keys())
                )

                if found is not None:
                    logger.error(
                        "Duplicate embedding detected: entry_id=%s first_file=%s second_file=%s",
                        entry_id, found_in_file, f
                    )
                    raise RuntimeError(f"Duplicate embedding found across dumps for {entry_id}")

                found = data[entry_id].astype(np.float32)
                found_in_file = f

    # --- Fallback to JSON ---
    for f in json_files:
        with open(f, "r", encoding="utf-8") as fh:
            data = json.load(fh)

        if entry_id in data:
            logger.warning(
                "Embedding key match in JSON file: entry_id=%s file=%s total_keys=%d",
                entry_id, f, len(data.keys())
            )

            if found is not None:
                logger.error(
                    "Duplicate embedding detected: entry_id=%s first_file=%s second_file=%s",
                    entry_id, found_in_file, f
                )
                raise RuntimeError(f"Duplicate embedding found across dumps for {entry_id}")

            found = np.array(data[entry_id], dtype=np.float32)
            found_in_file = f

    if found is None:
        raise RuntimeError(f"Embedding not found for entry_id {entry_id}")

    return found

def highlight_standout_clauses(clause_embeddings: np.ndarray, threshold: float = 0.7) -> list[bool]:
    """
    Identify clauses that are 'standout' relative to other clauses in the same entry.

    Each clause is compared to the mean of all other clauses via cosine similarity.
    If similarity < threshold, it is considered standout.

    Returns a list of booleans aligned with clause_embeddings.
    """
    n = len(clause_embeddings)
    if n == 0:
        return []

    standout_flags = []
    for i in range(n):
        other_embeddings = np.delete(clause_embeddings, i, axis=0)
        mean_other = other_embeddings.mean(axis=0)
        sim = cosine_similarity(clause_embeddings[i], mean_other)
        standout_flags.append(sim < threshold)

    return standout_flags