"""
app/helpers/similarity.py

Provides raw similarity computations for vector embeddings.
"""

import numpy as np
from typing import Optional

def compute_similarity(vec1: Optional[np.ndarray], vec2: Optional[np.ndarray]) -> float:
    """
    Compute cosine similarity between two vectors safely.
    
    Returns 0.0 if either vector is None, empty, or has zero norm.
    """
    if vec1 is None or vec2 is None:
        return 0.0
    if len(vec1) == 0 or len(vec2) == 0:
        return 0.0

    vec1 = np.asarray(vec1, dtype=float)
    vec2 = np.asarray(vec2, dtype=float)

    norm1 = np.linalg.norm(vec1)
    norm2 = np.linalg.norm(vec2)

    if norm1 == 0.0 or norm2 == 0.0:
        return 0.0

    similarity = float(np.dot(vec1, vec2) / (norm1 * norm2))
    return similarity
