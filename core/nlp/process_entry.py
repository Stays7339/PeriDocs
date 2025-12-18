# ==========================================
# core/nlp/process_entry.py
# save-state updated 202512171943
# ==========================================

from __future__ import annotations
import asyncio
import hashlib
from typing import Dict, Any
from datetime import datetime, timezone

from .embeddings import encrypt_text, get_embedding_async
from .pii import redact_pii
from .hash_utils import sha8_hash, staff_hash
from .crisis_detector import crisis_notification
from .crisis_recorder import append_crisis_record
from core.map.centroids import assign_vector_to_existing_centroids
from .clause_utils import split_into_clauses, sliding_window_clauses
import numpy as np

# ---------------- Async NLP Pipeline (Clause + User-Entry Level) ----------------
async def process_entry_async(text: str, user_ip: str, max_clause_words: int = 100) -> Dict[str, Any]:
    if not text.strip():
        raise ValueError("Empty or whitespace-only entry.")

    # ---------------- TIMESTAMP ----------------
    timestamp_utc = datetime.now(timezone.utc).isoformat()
    ip_salt = hashlib.sha256(user_ip.encode()).hexdigest()[:8]

    # ---------------- CRISIS CHECK ----------------
    crisis_msg = crisis_notification(text)
    if crisis_msg:
        sha8 = sha8_hash(text)

        record = {
            "timestamp_utc": timestamp_utc,
            "text": text,                 # raw text, NOT encrypted here
            "user_ip_hash": ip_salt,
            "sha8": sha8,
            "centroid_id": None,
            "crisis_flag": True,
        }

        append_crisis_record(record)  # encryption happens inside recorder

        # Return same encrypted payload for the sake of letting downstream code know that a crisis happened while also passing information along about this specific occurence of crisis.
        encrypted_text = encrypt_text(text)

        return {
            "sha8": sha8,
            "staff_hash": None,
            "pseudonym_hash": None,
            "encrypted_text": encrypted_text,
            "safe_text": None,
            "embedding": None,
            "clause_embeddings": None,
            "centroid_id": None,
            "centroid_distance": None,
            "crisis_flag": True,
            "timestamp_utc": timestamp_utc,
            "ip_salt": ip_salt,
            "crisis_warning": crisis_msg,
        }


    # ---------------- SAFE TEXT ----------------
    safe_text = redact_pii(text)
    encrypted_text = encrypt_text(safe_text)

    # ---------------- CLAUSE SPLIT ----------------
    clauses = split_into_clauses(safe_text)
    windows = sliding_window_clauses(clauses, max_words=max_clause_words)

    # ---------------- EMBEDDINGS ----------------
    clause_embeddings = await get_embedding_async(windows)  # handles single or list
    doc_embedding = np.mean(clause_embeddings, axis=0)  # document-level centroid

    # ---------------- CENTROID ASSIGNMENT ----------------
    centroid_id, centroid_distance = assign_vector_to_existing_centroids(doc_embedding)

    # ---------------- HASHES ----------------
    sha8 = sha8_hash(safe_text)
    staff_h = staff_hash(text, ip_salt)
    pseudonym_hash = hashlib.sha256((safe_text + ip_salt).encode()).hexdigest()[:8]

    return {
        "sha8": sha8,
        "staff_hash": staff_h,
        "pseudonym_hash": pseudonym_hash,
        "encrypted_text": encrypted_text,
        "safe_text": safe_text,
        "embedding": doc_embedding.tolist(),
        "clause_embeddings": [e.tolist() for e in clause_embeddings],
        "centroid_id": centroid_id,
        "centroid_distance": centroid_distance,
        "crisis_flag": False,
        "timestamp_utc": timestamp_utc,
        "ip_salt": ip_salt,
    }

# ---------------- Sync Wrapper ----------------
def process_entry(text: str, user_ip: str, max_clause_words: int = 100) -> Dict[str, Any]:
    import nest_asyncio
    nest_asyncio.apply()
    return asyncio.run(process_entry_async(text, user_ip, max_clause_words))
