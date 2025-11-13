# file: core/nlp/process_entry.py
"""
Core Entry Processing for PeriDocs
-----------------------------------
Purpose:
    Processes incoming user journal entries safely and asynchronously.

Flow of Events (Full Module + Function Flow):
    process_entry.py acts as the **central conductor** for one journal entry.

    1. Receive raw user text (potentially containing PII or crisis terms)
    2. Check for crisis phrases via crisis.py
         → If a crisis is detected:
               - Stop all further embedding/processing
               - Encrypt and return only crisis metadata
    3. Encrypt the full raw text for legal-only visibility
         → Uses encryption.py (encrypt_text)
    4. Redact PII for all further non-legal operations
         → Uses pii.py (redact_pii)
    5. Compute embedding + emotion features in one pass via:
         → text_processing.py → text_processing.process_text()
               - Handles all embedding generation, normalization, and
                 emotion/valence/arousal profiling.
               - Ensures emotion_analysis.py and embeddings.py only run once.
    6. Tokenize and extract semantic anchors locally
         → tokenize_text() + extract_entities()
    7. Generate security + moderation hashes
         → sha8_hash() (public) + staff_hash() (internal)
    8. Compute repetition pattern weighting
         → repetition_echo.py (repetition_score)
    9. Assemble structured result for persistence:
         - encrypted_text (legal-only)
         - safe_text (redacted)
         - embeddings (non-reversible vector)
         - emotion summaries (from text_processing())
         - pseudonym + public hashes
         - repetition multiplier
         - metadata (timestamp, ip_salt)

Guarantees:
    - Only one call to emotion_analysis.py (indirectly via text_processing.py)
    - No redundant emotion or embedding computation
    - Fully async-safe processing with deterministic hashes

Key Dependencies:
    * crisis.py              → crisis_notification()
    * pii.py                 → redact_pii()
    * text_processing.py     → process_text()
    * embeddings.py          → encrypt_text()
    * repetition_echo.py     → repetition_score()
    * hash_utils.py          → sha8_hash(), staff_hash()
    * encryption.py          → encrypt_text() (legal-only storage)
"""

from __future__ import annotations
import asyncio
import hashlib
import re
from typing import Dict, Any, List
import numpy as np
from datetime import datetime, timezone
from rapidfuzz import fuzz, process as fuzz_process

from .text_processing import process_text  # <-- added import
from .embeddings import encrypt_text
from .pii import redact_pii
from .repetition_echo import repetition_score
from .hash_utils import sha8_hash, staff_hash
from .crisis import crisis_notification
from .encryption import encrypt_text as encrypt_legal_only
from .emotion_analysis import apply_intensity_modifiers  

# ---------------- RapidFuzz-based Tokenization & Entity Extraction ----------------

def tokenize_text(text: str) -> list[dict]:
    tokens = re.findall(r"\b\w+\b", text.lower())
    return [{"text": t, "lemma": t, "pos": "X", "is_stop": False} for t in tokens]

KNOWN_ENTITIES = [
    "depression", "anxiety", "suicide", "panic", "trauma", "relationship",
    "money", "grief", "anger", "fear", "stress", "loneliness", "health",
    "love", "work", "family", "addiction", "pain", "hope", "school"
]

def extract_entities(text: str) -> list[dict]:
    entities = []
    for word in set(re.findall(r"\b[A-Za-z][a-z]+\b", text)):
        match = fuzz_process.extractOne(word.lower(), KNOWN_ENTITIES, scorer=fuzz.ratio)
        if match and match[1] > 85:
            entities.append({"text": word, "label": match[0]})
    return entities

# ---------------- CORE PROCESSING ----------------
async def process_entry_async(text: str, user_ip: str) -> Dict[str, Any]:
    """
    Processes a user journal entry.
    Arguments:
        text (str): Original user input
        user_ip (str): Raw IP of user (encrypted/legal-only storage + IP salt)
    Returns:
        Dict[str, Any]: structured entry data
    """
    # ---------------- CRISIS CHECK ----------------
    crisis_msg = crisis_notification(text)
    if crisis_msg:
        encrypted_text = encrypt_text(text)
        legal_ip = encrypt_legal_only(user_ip)
        return {
            "crisis_warning": crisis_msg,
            "encrypted_text": encrypted_text,
            "legal_ip": legal_ip,
            "timestamp_utc": datetime.now(timezone.utc).isoformat()
        }

    # ---------------- SAFE TEXT ----------------
    safe_text = redact_pii(text)

    # ---------------- TEXT PROCESSING (Embedding + Emotion) ----------------
    cleaned, token_dicts, token_strings, features = process_text(text)

    embedding_vector = features.get("embedding_vector")
    embedding = embedding_vector.tolist() if embedding_vector is not None else None
    emotion_distribution = features.get("embedding_emotion_distribution", {})
    valence_arousal = features.get("valence_arousal_summary", {})

    # ---------------- NEW: Weighted Emotion Distribution ----------------
    # Apply intensity modifiers to produce the weighted distribution
    weighted_emotion_distribution = apply_intensity_modifiers(text, emotion_distribution)

    # ---------------- TOKENS & ENTITIES ----------------
    tokens = tokenize_text(safe_text)
    entities = extract_entities(safe_text)

    # ---------------- HASHES ----------------
    sha8 = sha8_hash(safe_text)
    ip_salt = hashlib.sha256(user_ip.encode("utf-8")).hexdigest()[:8]
    staff_h = staff_hash(text, ip_salt)

    # ---------------- REPETITION ----------------
    repetition = repetition_score(safe_text)

    # ---------------- TIMESTAMP ----------------
    timestamp_utc = datetime.now(timezone.utc).isoformat()

    return {
        "sha8": sha8,
        "staff_hash": staff_h,
        "encrypted_text": encrypt_text(text),
        "safe_text": safe_text,
        "tokens": tokens,
        "entities": entities,
        "embedding": embedding,
        "repetition_multiplier": repetition,
        "emotions": {
            "embedding_emotion_distribution": emotion_distribution,
            "valence_arousal_summary": valence_arousal,
            "weighted_emotion_distribution": weighted_emotion_distribution  # <-- added key
        },
        "emotion": {
            "distribution": weighted_emotion_distribution,  # <-- update to post-intensity
            "summary": valence_arousal
        },
        "timestamp_utc": timestamp_utc,
        "ip_salt": ip_salt
    }

# ---------------- SYNCHRONOUS WRAPPER ----------------
def process_entry(text: str, user_ip: str) -> Dict[str, Any]:
    """Synchronous wrapper for process_entry_async"""
    return asyncio.run(process_entry_async(text, user_ip))
