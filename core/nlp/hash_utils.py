
# ==========================================
# core/nlp/hash_utils.py
# save-state 2026-03-24T18:44:40-04:00
# Provides hashing utilities for generating unique IDs for entries.
# ==========================================

import hashlib

def full_hash(text: str) -> str:
    if not isinstance(text, str):
        raise TypeError("full_hash() requires a string input")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()