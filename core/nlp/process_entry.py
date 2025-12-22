# ==========================================
# core/nlp/process_entry.py
# updated 202512221511
# ==========================================

from __future__ import annotations
import asyncio
import hashlib
from typing import Dict, Any
from datetime import datetime, timezone
from pathlib import Path
from glob import glob
import json
import numpy as np

from .embeddings import encrypt_text, get_embedding_async
from .pii import redact_pii
from .hash_utils import sha8_hash
from .crisis_detector import crisis_notification_async
from .crisis_recorder import append_crisis_record
from core.map.centroids import assign_vector_to_existing_centroids
from .clause_utils import split_into_clauses, sliding_window_clauses

# ---- BACKUP / TIMESTAMPED EMBEDDINGS ----
now = datetime.now(timezone.utc)
window = now.hour // 6
BACKUP_TIMESTAMP = now.strftime("%Y%m%d") + f"_{window}"
JOURNALS_EMBED_FILE = f"data/journals_embeddings_dump{BACKUP_TIMESTAMP}.json"
JOURNALS_CLAUSE_EMBED_FILE = f"data/journals_embeddings_dump{BACKUP_TIMESTAMP}_clauses.json"

# Glob for existing embeddings (to validate file location / expected path)
existing_embed_files = sorted(glob("data/journals_embeddings_dump*.json"))
existing_clause_embed_files = sorted(glob("data/journals_embeddings_dump*_clauses.json"))

async def process_entry_async(text: str, user_ip: str, max_clause_words: int = 100) -> Dict[str, Any]:
    if not text.strip():
        raise ValueError("Empty or whitespace-only entry.")

    timestamp = datetime.now(timezone.utc).isoformat()
    ip_salt = hashlib.sha256(user_ip.encode()).hexdigest()[:8]

    # ---------------- CRISIS CHECK ----------------
    crisis_msg = await crisis_notification_async(text)
    if crisis_msg:
        sha8 = sha8_hash(text)
        record = {
            "timestamp": timestamp,
            "text": text,
            "user_ip_hash": ip_salt,
            "sha8": sha8,
            "centroid_id": None,
            "crisis_flag": True,
        }
        append_crisis_record(record)
        encrypted_text = encrypt_text(text)
        return {
            "sha8": sha8,
            "encrypted_text": encrypted_text,
            "safe_text": None,
            "embedding": None,
            "clause_embeddings": None,
            "centroid_id": None,
            "centroid_distance": None,
            "crisis_flag": True,
            "timestamp": timestamp,
            "ip_salt": ip_salt,
            "crisis_warning": crisis_msg,
            "embedding_file": JOURNALS_EMBED_FILE,
            "clause_embedding_file": JOURNALS_CLAUSE_EMBED_FILE
        }

    # ---------------- SAFE TEXT ----------------
    safe_text = redact_pii(text)
    encrypted_text = encrypt_text(safe_text)

    # ---------------- CLAUSE SPLIT ----------------
    clauses = split_into_clauses(safe_text)
    windows = sliding_window_clauses(clauses, max_words=max_clause_words)

    # ---------------- EMBEDDINGS ----------------
    clause_embeddings = await get_embedding_async(windows)
    doc_embedding = np.mean(clause_embeddings, axis=0)

    # ---------------- CENTROID ASSIGNMENT ----------------
    centroid_id, centroid_distance = assign_vector_to_existing_centroids(doc_embedding)

    # ---------------- HASH ----------------
    sha8 = sha8_hash(safe_text)

    # ---------------- RETURN FULL ENTRY ----------------
    return {
        "sha8": sha8,
        "encrypted_text": encrypted_text,
        "safe_text": safe_text,
        "embedding": doc_embedding.tolist(),
        "clause_embeddings": [e.tolist() for e in clause_embeddings],
        "centroid_id": centroid_id,
        "centroid_distance": centroid_distance,
        "crisis_flag": False,
        "timestamp": timestamp,
        "ip_salt": ip_salt,
        "embedding_file": JOURNALS_EMBED_FILE,
        "clause_embedding_file": JOURNALS_CLAUSE_EMBED_FILE
    }


# ---------------- Sync Wrapper ----------------
def process_entry(text: str, user_ip: str, max_clause_words: int = 100) -> Dict[str, Any]:
    import nest_asyncio
    nest_asyncio.apply()
    return asyncio.run(process_entry_async(text, user_ip, max_clause_words))
