"""
file: core/nlp/process_entry.py
save-state updated 202511241352 (date and time formatted as follows: YYYYMMDDhhmm)
orchestrates full entry processing including crisis handling, PII redaction, tokenization, 
embedding + emotion extraction, repetition scoring, hashing, sentiment, and summary. 
It wraps an async pipeline with a synchronous helper.
"""
from __future__ import annotations
import asyncio
import hashlib
import re
from typing import Dict, Any
import numpy as np
from datetime import datetime, timezone
from rapidfuzz import fuzz, process as fuzz_process

from .text_processing import process_text
from .embeddings import encrypt_text
from .pii import redact_pii
from .repetition_echo import repetition_score
from .hash_utils import sha8_hash, staff_hash
from .crisis import crisis_notification
from .encryption import encrypt_text as encrypt_legal_only
from .emotion_analysis import (
    compute_sentiment_from_valence_arousal,
    analyze_emotions_async,
    normalize_emotion_profile
)
from core.nlp.anchors import EMOTION_ALIASES, CANONICAL_EMOTIONS


# ---------------- Tokenization & Entity Extraction ----------------

def tokenize_text(text: str) -> list[dict]:
    tokens = re.findall(r"\b\w+\b", text.lower())
    return [{"text": t, "lemma": t, "pos": "X", "is_stop": False} for t in tokens]

KNOWN_ENTITIES = [
    "depression", "anxiety", "suicide", "panic", "trauma", "relationship",
    "money", "grief", "anger", "fear", "stress", "loneliness", "health",
    "love", "work", "family", "addiction", "pain", "hope", "school"
]

def extract_entities(text: str) -> list[dict]:
    text_lower = text.lower()
    words = set(re.findall(r"\b[a-zA-Z][a-z]+\b", text_lower))

    # Combine canonical labels + alias targets
    target_labels = set(CANONICAL_EMOTIONS)

    threshold = 78

    results = []
    for w in words:
        base = EMOTION_ALIASES.get(w, w)
        match = fuzz_process.extractOne(base, list(target_labels), scorer=fuzz.ratio)
        if match and match[1] >= threshold:
            results.append({"text": w, "label": match[0]})
    return results

# ---------------- Async NLP Pipeline ----------------

async def process_entry_async(text: str, user_ip: str) -> Dict[str, Any]:
    # ---------------- CRISIS CHECK ----------------
    crisis_msg = crisis_notification(text)
    if crisis_msg:
        from .crisis_writer import append_crisis_record
        try:
            append_crisis_record({
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "text": text,
                "user_ip_hash": hashlib.sha256(user_ip.encode("utf-8")).hexdigest()[:8],
            })
        except Exception as e:
            raise RuntimeError(f"Failed to write crisis record: {e}") from e

        encrypted_text = encrypt_text(text)
        legal_ip = encrypt_legal_only(user_ip)
        ip_salt = hashlib.sha256(user_ip.encode("utf-8")).hexdigest()[:8]

        # Inside the CRISIS_CHECK block, after your existing return dictionary:
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
            "emotions": {},
            "emotion": {},
            "sentiment": {"polarity": 0.0, "label": "crisis"},
            "summary": {"primary_emotion": "neutral", "intensity": 0.0, "valence_arousal": {}},
            "crisis_flag": True,
            "weighted_emotion_distribution": {},
            "emotion_distribution": {},
            "dominant_emotion": "neutral",   # <-- added line
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "ip_salt": ip_salt,
            "crisis_warning": crisis_msg,
            "legal_ip": legal_ip
        }

    # ---------------- SAFE TEXT ----------------
    safe_text = redact_pii(text)

    # ------- EMBEDDING RAW TEXT FOR PROACTIVE LEGAL PURPOSES ONLY -----
    encrypted_text = encrypt_text(safe_text)
    # ---------------- TEXT PROCESSING ----------------
    cleaned, _, _, features = process_text(text)
    embedding_vector = features.get("embedding_vector")
    embedding_mean = float(np.mean(embedding_vector)) if embedding_vector is not None else 0.0

    # Async weighted emotion computation
    async_result = await analyze_emotions_async(text)
    weighted_emotion_distribution = normalize_emotion_profile(
        async_result.get("emotion_distribution", {})
    )
    valence_arousal = async_result.get("valence_arousal_summary", {})

    # ---------------- TOKENS & ENTITIES ----------------
    tokens = tokenize_text(safe_text)
    entities = extract_entities(safe_text)

    # ---------------- HASHES ----------------
    sha8 = sha8_hash(safe_text)
    ip_salt = hashlib.sha256(user_ip.encode("utf-8")).hexdigest()[:8]
    staff_h = staff_hash(text, ip_salt)
    pseudonym_hash = hashlib.sha256((safe_text + ip_salt).encode("utf-8")).hexdigest()[:8]

    # ---------------- REPETITION ----------------
    repetition = repetition_score(safe_text)

    # ---------------- DOMINANT EMOTION ----------------
    dominant_emotion = None
    if weighted_emotion_distribution:
        dominant_emotion = max(weighted_emotion_distribution.items(), key=lambda kv: kv[1])[0]

    # ==========================================
    # BUILD emotion_block FOR BACKWARD COMPATIBILITY
    # ==========================================
    emotion_block = {
        "distribution": weighted_emotion_distribution,
        "valence_arousal": valence_arousal
    }

    # ==========================================
    # NON-CRISIS RETURN PAYLOAD
    # ==========================================
    return {
        "sha8": sha8,
        "staff_hash": staff_h,
        "pseudonym_hash": pseudonym_hash,
        "encrypted_text": encrypt_text(text),
        "safe_text": safe_text,
        "tokens": tokens,
        "entities": entities,
        "embedding": embedding_vector,
        "embedding_mean": embedding_mean,
        "repetition_multiplier": repetition,

        # canonical new interface
        "emotions": {
            "weighted": weighted_emotion_distribution,
            "valence_arousal": valence_arousal,
        },

        # restored for API stability **(YOUR TESTS DEPEND ON THIS KEY)**
        "emotion": emotion_block,

        "dominant_emotion": dominant_emotion,
        "crisis_flag": False,

        # legacy field names preserved for transition period
        "weighted_emotion_distribution": weighted_emotion_distribution,
        "emotion_distribution": weighted_emotion_distribution,

        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "ip_salt": ip_salt
    }

# ---------------- SYNCHRONOUS WRAPPER ----------------
def process_entry(text: str, user_ip: str) -> Dict[str, Any]:
    return asyncio.run(process_entry_async(text, user_ip))

# ---------------- FRONTEND EMOTION PERCENTAGES ----------------
def compute_weighted_emotion_distribution(entry_text, emotion_model):
    weighted_emotion_distribution = emotion_model.predict(entry_text)
    total_weight = sum(weighted_emotion_distribution.values()) or 1.0
    emotion_distribution_str = {
        k: f"{(v / total_weight * 100):.1f}%" for k, v in weighted_emotion_distribution.items()
    }
    return weighted_emotion_distribution, emotion_distribution_str

# ---------------- TOP MATCHES ----------------
def get_top_matches(entry_embedding, embeddings_index, top_n=20):
    """
    Returns top N matches by cosine similarity.

    Parameters:
        entry_embedding (list or np.array): normalized vector of current entry
        embeddings_index (dict): mapping of entry_id -> normalized vector
        top_n (int): number of top matches to return

    Returns:
        list of tuples: [(entry_id, similarity), ...] sorted descending
    """
    import numpy as np

    if entry_embedding is None:
        return []

    # Ensure entry_embedding is a NumPy array
    entry_vec = np.array(entry_embedding, dtype=np.float32)
    norm_entry = np.linalg.norm(entry_vec)
    if norm_entry == 0:
        return []  # skip zero vectors

    similarities = []
    for eid, vec in embeddings_index.items():
        vec_arr = np.array(vec, dtype=np.float32)
        norm_vec = np.linalg.norm(vec_arr)
        if norm_vec == 0:
            continue  # skip zero vectors
        # Cosine similarity
        sim = float(np.dot(entry_vec, vec_arr) / (norm_entry * norm_vec))
        similarities.append((eid, sim))

    # Sort descending and return top N
    similarities.sort(key=lambda x: x[1], reverse=True)
    return similarities[:top_n]

def normalize_vector(vec):
    """Return unit vector as NumPy array for computation, optionally .tolist() when saving."""
    if vec is None:
        return None
    arr = np.array(vec, dtype=float)
    norm = np.linalg.norm(arr)
    if norm == 0:
        return arr  # keep as array
    return arr / norm


# ---------------- MAKING FLOATS INTO PERCS ----------------
def format_emotion_distribution(dist: dict) -> dict:
    total = sum(dist.values()) or 1.0
    return {k: f"{(v/total*100):.1f}%" for k,v in dist.items()}
