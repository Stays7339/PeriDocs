# ==========================================
# core/nlp/hash_utils.py
# save-state 2026-03-19T1803:10-04:00
#Provides SHA8 hashing utilities for generating unique IDs for entries.
# ==========================================

import hashlib

def sha8_hash(text: str) -> str:
    """
    Generate a short SHA-256-based hash (first 8 hex characters) for the given text.
    
    When generating 100,000 SHA-256 hashes truncated to 8 characters, 
    there's about a 2.23% chance of a repeat; with 1,000,000 hashes, 
    that chance jumps to nearly 100% due to the nature of how hashes can collide.
    """
    if not isinstance(text, str):
        raise TypeError("sha8_hash() requires a string input")
    
    full_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return full_hash[:8]

def full_hash_instead(text: str) -> str:
    """
    Generate the full SHA-256-based hash for the given text.
    """
    if not isinstance(text, str):
        raise TypeError("sha8_hash() requires a string input")
    
    full_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return full_hash_instead