"""
PeriDocs-code/core/nlp/process_entry.py
Save-state: 202512121235 -> updated for Option 1

Async + sync entry processing pipeline for PeriDocs.
- Embedding-based emotion detection only
- Normalized emotion distributions
- Tokens, entities, repetition, embedding handling
- No sentiment or valence/arousal
"""

from __future__ import annotations
import asyncio, hashlib, re
from typing import Dict, Any
import numpy as np
from datetime import datetime, timezone

from .text_processing import process_text_async
from .embeddings import encrypt_text
from .pii import redact_pii
from .repetition_echo import repetition_score
from .hash_utils import sha8_hash, staff_hash
from .crisis_detector import crisis_notification
from .encryption import encrypt_text as encrypt_legal_only
from .emotion_analysis import analyze_emotions_async, normalize_emotion_profile

# -------------------------------
# Tokens & entities
# -------------------------------
def tokenize_text(text: str) -> list[dict]:
    tokens = re.findall(r"\b\w+\b", text.lower())
    return [{"text": t, "lemma": t, "pos": "X"} for t in tokens]

def extract_entities(text: str) -> list[dict]:
    return []

# -------------------------------
# Async entry processing
# -------------------------------
async def process_entry_async(text: str, user_ip: str) -> Dict[str, Any]:
    # ----------------- Crisis Detection -----------------
    crisis_msg = await crisis_notification(text) if asyncio.iscoroutinefunction(crisis_notification) else crisis_notification(text)
    if crisis_msg:
        from .crisis_writer import append_crisis_record
        record = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "text": text,
            "user_ip_hash": hashlib.sha256(user_ip.encode("utf-8")).hexdigest()[:8],
        }
        if asyncio.iscoroutinefunction(append_crisis_record):
            await append_crisis_record(record)
        else:
            append_crisis_record(record)

        encrypted_text = encrypt_text(text)
        legal_ip = encrypt_legal_only(user_ip)
        ip_salt = hashlib.sha256(user_ip.encode("utf-8")).hexdigest()[:8]
        return {
            "encrypted_text": encrypted_text,
            "safe_text": None,
            "tokens": [],
            "entities": [],
            "embedding": None,
            "embedding_mean": 0.0,
            "repetition_multiplier": 0.0,
            "emotions": {},
            "crisis_flag": True,
            "ip_salt": ip_salt,
            "legal_ip": legal_ip,
            "text": text,
        }

    # ----------------- Safe Text & Embeddings -----------------
    safe_text = redact_pii(text)
    encrypted_text = encrypt_text(safe_text)
    cleaned, _, _, features = await process_text_async(text)
    embedding_vector = features.get("embedding_vector")
    if embedding_vector is None or np.linalg.norm(embedding_vector) < 1e-6:
        from .text_processing import _deterministic_fallback_vec
        embedding_vector = _deterministic_fallback_vec(text)
    embedding_mean = float(np.mean(embedding_vector))

    # Convert embedding to list for JSON safety
    embedding_vector_list = embedding_vector.tolist() if isinstance(embedding_vector, np.ndarray) else embedding_vector

    # ----------------- Embedding-driven Emotion Analysis -----------------
    async_result = await analyze_emotions_async(text)
    weighted_emotion_distribution = normalize_emotion_profile(async_result.get("emotions", {}))

    # ----------------- Tokens & Entities -----------------
    tokens = tokenize_text(safe_text)
    entities = extract_entities(safe_text)

    # ----------------- Hashes & Repetition -----------------
    sha8 = sha8_hash(safe_text)
    ip_salt = hashlib.sha256(user_ip.encode("utf-8")).hexdigest()[:8]
    staff_h = staff_hash(text, ip_salt)
    pseudonym_hash = hashlib.sha256((safe_text + ip_salt).encode("utf-8")).hexdigest()[:8]
    repetition = repetition_score(safe_text)

    emotion_block = {"distribution": weighted_emotion_distribution}

    # ----------------- Return -----------------
    return {
        "sha8": sha8,
        "staff_hash": staff_h,
        "pseudonym_hash": pseudonym_hash,
        "encrypted_text": encrypted_text,
        "safe_text": safe_text,
        "tokens": tokens,
        "entities": entities,
        "embedding": embedding_vector_list,
        "embedding_mean": embedding_mean,
        "repetition_multiplier": repetition,
        "emotions": weighted_emotion_distribution,
        "emotion": emotion_block,
        "crisis_flag": False,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "ip_salt": ip_salt,
        "text": text,
    }

# ---------------- TOP MATCHES ----------------
def get_top_matches(entry_embedding, embeddings_index, top_n=20):
    """
    Returns top N matches by cosine similarity.
    """
    if entry_embedding is None:
        return []

    entry_vec = np.array(entry_embedding, dtype=np.float32)
    norm_entry = np.linalg.norm(entry_vec)
    if norm_entry == 0:
        return []

    similarities = []
    for eid, vec in embeddings_index.items():
        vec_arr = np.array(vec, dtype=np.float32)
        norm_vec = np.linalg.norm(vec_arr)
        if norm_vec == 0:
            continue
        sim = float(np.dot(entry_vec, vec_arr) / (norm_entry * norm_vec))
        similarities.append((eid, sim))

    similarities.sort(key=lambda x: x[1], reverse=True)
    return similarities[:top_n]

# -------------------------------
# Synchronous wrapper
# -------------------------------
def process_entry(text: str, user_ip: str) -> Dict[str, Any]:
    """
    Safe sync wrapper: uses asyncio.run if no loop is running,
    otherwise creates a temporary task in the existing loop.
    """
    try:
        loop = asyncio.get_running_loop()
        if loop.is_running():
            return asyncio.run_coroutine_threadsafe(process_entry_async(text, user_ip), loop).result()
        else:
            return asyncio.run(process_entry_async(text, user_ip))
    except RuntimeError:
        return asyncio.run(process_entry_async(text, user_ip))
