# file: core/nlp/process_entry.py
# updated 20251121 (date and time formatted as follows: YYYYMMDDhhmm)

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
from .emotion_analysis import (
    apply_intensity_modifiers,
    compute_sentiment_from_profile,
)

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
    Processes a user journal entry with privacy-preserving crisis handling.
    """

    # ---------------- CRISIS CHECK ----------------
    crisis_msg = crisis_notification(text)
    if crisis_msg:
        # ======================================================================
        # EARLY RETURN FOR CRISIS TEXT
        # ======================================================================
        # Intentionally skipping embeddings, emotion computation, tokenization, etc.
        # All keys are returned but set to None or empty dict/list. This is intentional.
        # Anyone inspecting the output should immediately see that no NLP processing
        # was performed due to crisis content.
        # ======================================================================

        # Log to terminal for executive/debug inspection
        print("\n" + "="*80)
        print("!!! CRISIS ENTRY DETECTED !!!")
        print("Original Text:", text)
        print("NOTE: All None or empty values below are INTENTIONAL for crisis entries.")
        print("NLP computations are skipped; this is by design.")
        print("="*80 + "\n")

        from .crisis_writer import append_crisis_record

        try:
            append_crisis_record({
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "text": text,
                "user_ip_hash": hashlib.sha256(user_ip.encode("utf-8")).hexdigest()[:8],
            })
        except Exception as e:
            # Explicitly raise, do not silently ignore
            raise RuntimeError(f"Failed to write crisis record: {e}") from e

        encrypted_text = encrypt_text(text)
        legal_ip = encrypt_legal_only(user_ip)
        ip_salt = hashlib.sha256(user_ip.encode("utf-8")).hexdigest()[:8]

        return {
            "sha8": None,
            "staff_hash": None,
            "pseudonym_hash": None,
            "encrypted_text": encrypted_text,
            "safe_text": None,
            "tokens": [],
            "entities": [],
            "embedding": None,
            "embedding_mean": 0.0,
            "repetition_multiplier": 0.0,
            "emotions": {},  # intentionally empty
            "emotion": {},   # intentionally empty
            "sentiment": {"polarity": 0.0, "label": "neutral"},  # safe default
            "summary": {
                "primary_emotion": "neutral",
                "intensity": 0.0,
                "valence_arousal": {}
            },
            "crisis_flag": True,
            "weighted_emotion_distribution": {},
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "ip_salt": ip_salt,
            "crisis_warning": crisis_msg,
            "legal_ip": legal_ip
        }

    # ---------------- SAFE TEXT ----------------
    safe_text = redact_pii(text)

    # ---------------- TEXT PROCESSING (Embedding + Emotion) ----------------
    cleaned, token_dicts, token_strings, features = process_text(text)

    embedding_vector = features.get("embedding_vector")

    if embedding_vector is None:
        # Only use fallback for empty or failed embedding (non-crisis)
        embedding = None
        embedding_mean = 0.0
        # Attempt to use whatever the process_text returned for emotions, else default empty
        emotion_distribution = features.get("embedding_emotion_distribution") or {}
        valence_arousal = features.get("valence_arousal_summary") or {}
        weighted_emotion_distribution = apply_intensity_modifiers(text, emotion_distribution)
    else:
        embedding = embedding_vector
        embedding_mean = float(np.mean(embedding))
        emotion_distribution = features.get("embedding_emotion_distribution", {})
        valence_arousal = features.get("valence_arousal_summary", {})
        weighted_emotion_distribution = apply_intensity_modifiers(text, emotion_distribution)

    # Tokens & Entities
    tokens = tokenize_text(safe_text)
    entities = extract_entities(safe_text)

    # Hashes
    sha8 = sha8_hash(safe_text)
    ip_salt = hashlib.sha256(user_ip.encode("utf-8")).hexdigest()[:8]
    staff_h = staff_hash(text, ip_salt)
    pseudonym_hash = hashlib.sha256((safe_text + ip_salt).encode("utf-8")).hexdigest()[:8]

    # Repetition
    repetition = repetition_score(safe_text)

    # Timestamp
    timestamp_utc = datetime.now(timezone.utc).isoformat()

    # Sentiment (explicit errors propagate)
    if valence_arousal and "valence" in valence_arousal:
        sentiment = compute_sentiment_from_profile(valence_arousal)
    else:
        sentiment = {"polarity": 0.0, "label": "neutral"}

    # Summary
    primary_emotion = "neutral"
    intensity = 0.0
    if weighted_emotion_distribution:
        primary_emotion = max(weighted_emotion_distribution, key=lambda k: weighted_emotion_distribution.get(k, 0.0))
        intensity = float(max(weighted_emotion_distribution.values(), default=0.0))

    crisis_flag = False

    return {
        "sha8": sha8,
        "staff_hash": staff_h,
        "pseudonym_hash": pseudonym_hash,
        "encrypted_text": encrypt_text(text),
        "safe_text": safe_text,
        "tokens": tokens,
        "entities": entities,
        "embedding": embedding,
        "embedding_mean": embedding_mean,
        "repetition_multiplier": repetition,
        "emotions": {
            "embedding_emotion_distribution": emotion_distribution,
            "valence_arousal_summary": valence_arousal,
            "weighted_emotion_distribution": weighted_emotion_distribution
        },
        "emotion": {
            "distribution": weighted_emotion_distribution,
            "summary": valence_arousal
        },
        "sentiment": sentiment,
        "summary": {
            "primary_emotion": primary_emotion,
            "intensity": intensity,
            "valence_arousal": valence_arousal
        },
        "crisis_flag": crisis_flag,
        "weighted_emotion_distribution": weighted_emotion_distribution,
        "timestamp_utc": timestamp_utc,
        "ip_salt": ip_salt
    }

# ---------------- SYNCHRONOUS WRAPPER ----------------
def process_entry(text: str, user_ip: str) -> Dict[str, Any]:
    """
    Synchronous wrapper for process_entry_async.
    
    Executes the async pipeline and returns results.
    Any exceptions in async processing (including crisis record writes)
    will propagate to the caller.
    """
    return asyncio.run(process_entry_async(text, user_ip))
