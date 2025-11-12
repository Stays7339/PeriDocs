"""
app/helpers/json_safe.py

Provides JSON-safe conversions for objects that may include
NumPy arrays, sets, or other non-serializable types.
"""

import json
import numpy as np
from typing import Any

def json_safe(obj: Any) -> Any:
    """
    Recursively converts obj into a JSON-serializable format.

    Handles:
      - NumPy arrays → list
      - NumPy scalar types → native Python types
      - sets → list
      - dicts → recursively applied
      - lists/tuples → recursively applied
      - other types left as-is if serializable
    """
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, (np.generic,)):
        return obj.item()
    elif isinstance(obj, dict):
        return {k: json_safe(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple, set)):
        return [json_safe(v) for v in obj]
    else:
        try:
            json.dumps(obj)  # test if serializable
            return obj
        except (TypeError, OverflowError):
            return str(obj)
