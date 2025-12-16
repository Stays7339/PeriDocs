# ==========================================
# core/nlp/process_entry.py
# save-state updated 202512161521
# ==========================================

from __future__ import annotations
import asyncio
import hashlib
from typing import Dict, Any
from datetime import datetime, timezone

from .embeddings import encrypt_text, get_embedding_async
from .pii import redact_pii
from .hash_utils import sha8_hash, staff_hash
from .crisis import crisis_notification
from .crisis_writer import append_crisis_record
from .emotion_analysis import compute_emotion_profile_async, normalize_emotion_profile
from core.map.centroids import assign_to_centroid

# ---------------- Async NLP Pipeline ----------------
async def process_entry_async(text: str, user_ip: str) -> Dict[str, Any]:
    if not text.strip():
        raise ValueError("Empty or whitespace-only entry.")

    # ---------------- CRISIS CHECK ----------------
    crisis_msg = crisis_notification(text)
    if crisis_msg:
        append_crisis_record({
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "text": text,
            "user_ip_hash": hashlib.sha256(user_ip.encode()).hexdigest()[:8],
        })

        encrypted_text = encrypt_text(text)
        ip_salt = hashlib.sha256(user_ip.encode()).hexdigest()[:8]

        return {
            "sha8": None,
            "staff_hash": None,
            "pseudonym_hash": None,
            "encrypted_text": encrypted_text,
            "safe_text": None,
            "embedding": None,
            "centroid_id": None,
            "centroid_distance": None,
            "crisis_flag": True,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "ip_salt": ip_salt,
            "crisis_warning": crisis_msg,
        }

    # ---------------- SAFE TEXT ----------------
    safe_text = redact_pii(text)
    encrypted_text = encrypt_text(safe_text)

    # ---------------- EMBEDDING ----------------
    embedding_vector = await get_embedding_async(safe_text)

    # ---------------- CENTROID ASSIGNMENT ----------------
    centroid_id, centroid_distance = assign_to_centroid(embedding_vector)

    # ---------------- HASHES ----------------
    sha8 = sha8_hash(safe_text)
    ip_salt = hashlib.sha256(user_ip.encode()).hexdigest()[:8]
    staff_h = staff_hash(text, ip_salt)
    pseudonym_hash = hashlib.sha256((safe_text + ip_salt).encode()).hexdigest()[:8]

    # ---------------- EMOTION PROFILE ----------------
    emotion_profile = await compute_emotion_profile_async(safe_text)
    emotions = normalize_emotion_profile(emotion_profile)
    dominant_emotion = max(emotions, key=emotions.get) if emotions else None

    return {
        "sha8": sha8,
        "staff_hash": staff_h,
        "pseudonym_hash": pseudonym_hash,
        "encrypted_text": encrypted_text,
        "safe_text": safe_text,
        "embedding": embedding_vector.tolist(),
        "centroid_id": centroid_id,
        "centroid_distance": centroid_distance,
        "crisis_flag": False,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "ip_salt": ip_salt,
        "emotions": emotions,
        "dominant_emotion": dominant_emotion,
        "centroid_id": centroid_id,
        "centroid_distance": centroid_distance,
    }

def process_entry(text: str, user_ip: str) -> Dict[str, Any]:
    import nest_asyncio
    nest_asyncio.apply()
    return asyncio.run(process_entry_async(text, user_ip))
