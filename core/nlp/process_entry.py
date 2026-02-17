# ==========================================
# core/nlp/process_entry.py
# save-state 202602171615 (YYYYMMDDhhmm)
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
from .clause_utils import split_into_clauses, sliding_window_clauses
from core.map.mapping_runtime import centroid_system
from core.map import entry_membership_sequencer



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

    # ---------------- DYNAMIC PROGRESS LOADING STATUS SETUP ----------------
    steps = ["safe_text", "clause_split", "generate_embedding", "id_generation", "crisis_check", "construct_entry","persist_embedding_only_if_no_crisis","centroid_or_precentroid_linking"]
    #the labels in steps are purely descriptive for tracking which logical step is happening; they aren’t pulled from anywhere else in the repo.
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

    # ---------------- GENERATE EMBEDDING ----------------
    clause_embeddings = await get_embedding_async(windows)
    doc_embedding = np.mean(clause_embeddings, axis=0)
    report_progress()  # 3 / total_steps

    # ---------------- ID GENERATION ----------------
    sha8 = sha8_hash(safe_text)
    report_progress()  # 4 / total_steps
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
        "centroid_id": None, # handled downstream by core/map/*
        "centroid_distance": None, # handled downstream by core/map/*
        "embedding": None if crisis_msg else doc_embedding.tolist(),
        "embedding_file": None if crisis_msg else JOURNALS_EMBED_FILE,
        "clause_embeddings": [] if crisis_msg else [e.tolist() for e in clause_embeddings],
        "clause_embedding_file": None if crisis_msg else JOURNALS_CLAUSE_EMBED_FILE
    }

    append_crisis_record(entry)  # store exactly what will be returned
    report_progress()  # 6 / total_steps

    # ---------------- PERSIST EMBEDDINGS (only if no crisis) ----------------
    if not crisis_msg:
        Path("data").mkdir(exist_ok=True)

        # load existing journal embeddings
        if Path(JOURNALS_EMBED_FILE).exists():
            with open(JOURNALS_EMBED_FILE, "r", encoding="utf-8") as f:
                journal_dump = json.load(f)
        else:
            journal_dump = {}

        journal_dump[sha8] = doc_embedding.tolist()
        with open(JOURNALS_EMBED_FILE, "w", encoding="utf-8") as f:
            json.dump(journal_dump, f, indent=2)

        # load existing clause embeddings
        """
        if Path(JOURNALS_CLAUSE_EMBED_FILE).exists():
            with open(JOURNALS_CLAUSE_EMBED_FILE, "r", encoding="utf-8") as f:
                clause_dump = json.load(f)
        else:
            clause_dump = {}

        clause_dump[sha8] = [e.tolist() for e in clause_embeddings]
        with open(JOURNALS_CLAUSE_EMBED_FILE, "w", encoding="utf-8") as f:
            json.dump(clause_dump, f, indent=2)
        """

    report_progress()  # 7 / total_steps

    # ---------------- CENTROID / PRECENTROID ASSIGNMENT ----------------
    precentroid_id = await entry_membership_sequencer.suggest_precentroid_for_journal(entry["journal_id"])
    entry["centroid_id"] = precentroid_id or None
    report_progress()  # 8 / total_steps

    return entry

# ---------------- Sync Wrapper (meaning not asynchronous) ----------------
def process_entry(text: str, user_ip: str, max_clause_words: int = 100) -> Dict[str, Any]:
    loop = asyncio.get_event_loop()
    if loop.is_running():
        # Run async safely if we're already in an event loop
        return loop.run_until_complete(process_entry_async(text, user_ip, max_clause_words))
    else:
        return asyncio.run(process_entry_async(text, user_ip, max_clause_words))