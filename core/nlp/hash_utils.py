"""
core.nlp.hash_utils.py
save-state updated 202511231610 (date and time formatted as follows: YYYYMMDDhhmm)

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



def staff_hash(value: str, ip_salt: str = "") -> str:
    """
    Staff-only hash variant for moderation purposes.
    Uses the same base as sha8_hash but with a distinct 'staff:' prefix
    and optional IP-based salt to prevent cross-user collisions.
    """
    combined = f"staff:{ip_salt}:{value}".encode("utf-8")
    return hashlib.sha256(combined).hexdigest()[:8]
