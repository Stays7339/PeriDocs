# ==========================================
# app/helpers/entry_similarity.py
# Save-state: 202512172021
# Provides raw similarity computations for vector embeddings.
# ==========================================

import numpy as np
from typing import Optional

def compute_similarity_to_other_entries(
    vec1: Optional[np.ndarray],
    vec2: Optional[np.ndarray],
) -> float:
    if vec1 is None or vec2 is None:
        return 0.0

    vec1 = np.asarray(vec1, dtype=float)
    vec2 = np.asarray(vec2, dtype=float)

    # Guard against scalars / 0-d arrays
    if vec1.ndim == 0 or vec2.ndim == 0:
        return 0.0

    if vec1.size == 0 or vec2.size == 0:
        return 0.0

    norm1 = np.linalg.norm(vec1)
    norm2 = np.linalg.norm(vec2)

    if norm1 == 0.0 or norm2 == 0.0:
        return 0.0

    return float(np.dot(vec1, vec2) / (norm1 * norm2))
