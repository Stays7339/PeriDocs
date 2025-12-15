# ==========================================
# app/helpers/vector_ops.py
# save-state created 202512151600
# ==========================================
import numpy as np
from typing import Optional, List

def normalize_vector(vec: Optional[List[float]]) -> Optional[List[float]]:
    """
    Returns a unit-normalized version of the input vector.
    If the input is None, returns None.
    """
    if vec is None:
        return None
    arr = np.array(vec)
    norm = np.linalg.norm(arr)
    return (arr / norm).tolist() if norm > 0 else arr.tolist()
