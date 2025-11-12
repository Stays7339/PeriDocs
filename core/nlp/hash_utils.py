"""
core.nlp.hash_utils.py

Provides SHA8 hashing utilities for generating unique IDs for entries.
"""

import hashlib

def sha8_hash(text: str) -> str:
    """
    Generate a short SHA-256-based hash (first 8 hex characters) for the given text.
    
    Args:
        text (str): Input string to hash.
    
    Returns:
        str: 8-character hexadecimal hash.
    """
    if not isinstance(text, str):
        raise TypeError("sha8_hash() requires a string input")
    
    full_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return full_hash[:8]
