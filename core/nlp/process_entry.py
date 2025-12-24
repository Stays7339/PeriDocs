# ==========================================
# core/nlp/process_entry.py
# save-state 202512241139 (YYYYMMDDhhmm)
# ==========================================

from __future__ import annotations
import asyncio
import hashlib
from typing import Dict, Any, Callable
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

async def process_entry_async(
    text: str,
    user_ip: str,
    max_clause_words: int = 100,
    progress_callback: Callable[[float], None] | None = None
) -> Dict[str, Any]:
    if not text.strip():
        raise ValueError("Empty or whitespace-only entry.")

    timestamp = datetime.now(timezone.utc).isoformat()
    ip_salt = hashlib.sha256(user_ip.encode()).hexdigest()[:8]
    encrypted_raw_ip = encrypt_text(user_ip)
    encrypted_raw_text = encrypt_text(text)

    # ---------------- DYNAMIC PROGRESS SETUP ----------------
    steps = ["safe_text", "clause_split", "embeddings", "centroid", "crisis_check"]
    total_steps = len(steps)
    current_step = 0
    def report_progress():
        nonlocal current_step
        current_step += 1
        if progress_callback:
            progress_callback(current_step / total_steps)

    # ---------------- SAFE TEXT ----------------
    safe_text = redact_pii(text)
    encrypted_safe_text = encrypt_text(safe_text)
    report_progress()  # 1 / total_steps

    # ---------------- CLAUSE SPLIT ----------------
    clauses = split_into_clauses(safe_text)
    windows = sliding_window_clauses(clauses, max_words=max_clause_words)
    report_progress()  # 2 / total_steps

    # ---------------- EMBEDDINGS ----------------
    clause_embeddings = await get_embedding_async(windows)
    doc_embedding = np.mean(clause_embeddings, axis=0)
    report_progress()  # 3 / total_steps

    # ---------------- CENTROID ASSIGNMENT ----------------
    centroid_id, centroid_distance = await assign_vector_to_existing_centroids(doc_embedding)
    report_progress()  # 4 / total_steps

    # ---------------- HASH ----------------
    sha8 = sha8_hash(safe_text)

    # ---------------- CRISIS CHECK ----------------
    crisis_msg = await crisis_notification_async(text)
    report_progress()  # 5 / total_steps

    # ---------------- CONSTRUCT ENTRY ----------------
    entry: Dict[str, Any] = {
        "journal_id": sha8,
        "timestamp": timestamp,
        "ip_salt": ip_salt,
        "encrypted_raw_ip": encrypted_raw_ip,
        "encrypted_raw_text": encrypted_safe_text,
        "crisis_flag": bool(crisis_msg),
        "safe_text": "" if crisis_msg else safe_text,
        "centroid_id": None if crisis_msg else centroid_id,
        "centroid_distance": None if crisis_msg else centroid_distance,
        "embedding": None if crisis_msg else doc_embedding.tolist(),
        "embedding_file": None if crisis_msg else JOURNALS_EMBED_FILE,
        "clause_embeddings": [] if crisis_msg else [e.tolist() for e in clause_embeddings],
        "clause_embedding_file": None if crisis_msg else JOURNALS_CLAUSE_EMBED_FILE
    }

    append_crisis_record(entry)  # store exactly what will be returned

    return entry

# ---------------- Sync Wrapper ----------------
def process_entry(text: str, user_ip: str, max_clause_words: int = 100) -> Dict[str, Any]:
    import nest_asyncio
    nest_asyncio.apply()
    return asyncio.run(process_entry_async(text, user_ip, max_clause_words))
