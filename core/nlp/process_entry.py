# ==========================================
# core/nlp/process_entry.py
# save-state 202602241405(YYYYMMDDhhmm)
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
import secrets
import hashlib


from .embeddings import encrypt_text, get_embedding_async
from .pii import redact_pii
from .hash_utils import sha8_hash
from .crisis_detector import crisis_notification_async
from .crisis_recorder import append_crisis_record
from .clause_utils import split_into_clauses, sliding_window_clauses
from core.map.mapping_runtime import centroid_system
from core.map import entry_membership_sequencer
from app.helpers.file_ops import load_data


# ---- BACKUP / TIMESTAMPED EMBEDDINGS ----
now = datetime.now(timezone.utc)
window = now.hour // 6
BACKUP_TIMESTAMP = now.strftime("%Y%m%d") + f"_{window}"
entries_EMBED_FILE = f"data/entries_embeddings_dump{BACKUP_TIMESTAMP}.npz"

# Glob for existing embeddings (to validate file location / expected path)
existing_embed_files = sorted(glob("data/entries_embeddings_dump*.npz"))

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
    steps = ["safe_text", "clause_split", "generate_embedding", "id_generation", "crisis_check", "construct_entry","persist_embedding_only_if_no_crisis","centroid_or_precentroid_linking", "logic_for_delete_token"]
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
    doc_embedding = np.mean(clause_embeddings, axis=0).astype(np.float32)
    report_progress()  # 3 / total_steps

    # ---------------- ID GENERATION ----------------
    sha8 = sha8_hash(safe_text)

    # Compute full SHA256 first
    full_sha256 = hashlib.sha256(safe_text.encode("utf-8")).hexdigest()

    # Now compute truncated SHA8
    sha8 = full_sha256[:8]

    # Log both
    print(f"[DEBUG] Full SHA256: {full_sha256} | SHA8: {sha8}")
    report_progress()  # 4 / total_steps
    # ---------------- CRISIS CHECK ----------------
    crisis_msg = await crisis_notification_async(text)
    report_progress()  # 5 / total_steps

    # ---------------- CONSTRUCT ENTRY ----------------
    entry: Dict[str, Any] = {
        "entry_id": sha8,
        "timestamp": timestamp,
        "ip_salt": ip_salt,
        "encrypted_raw_ip": encrypted_raw_ip,
        "encrypted_raw_text": encrypted_safe_text,
        "crisis_flag": bool(crisis_msg),
        "safe_text": "" if crisis_msg else safe_text,
        "centroid_id": None, # handled downstream by core/map/*
        "centroid_distance": None, # handled downstream by core/map/*
        "embedding_file": None if crisis_msg else entries_EMBED_FILE,
        "embedding": None if crisis_msg else doc_embedding
    }

    # --------------------- CRISIS SHORT-CIRCUIT ---------------------
    if crisis_msg:
        # Record crisis entry safely
        append_crisis_record(entry)
        report_progress()  # 6 / total_steps
        # Return immediately so we skip embeddings/centroids
        return entry

    report_progress()  # 6 / total_steps

    # ---------------- PERSIST EMBEDDINGS (only if no crisis) ----------------
    if not crisis_msg:
        Path("data").mkdir(exist_ok=True)

        # --- Persist document embeddings as .npz ---
        npz_path = entries_EMBED_FILE

        if Path(npz_path).exists():
            # load safely, NO pickling
            loaded = dict(np.load(npz_path, allow_pickle=False))

            # validate keys
            for k in loaded.keys():
                if not isinstance(k, str) or len(k) != 8 or not all(c in "0123456789abcdef" for c in k.lower()):
                    raise RuntimeError(f"Unexpected key in NPZ dump: {k}")

            npz_dump = loaded
        else:
            npz_dump = {}

        npz_dump[sha8] = doc_embedding
        np.savez_compressed(npz_path, **npz_dump)

       
        """
         # load existing clause embeddings for the sake of saving it permanently. 
         # As long as this is commented out, per clause embeddings are disabled.
         # That's good for storage space, but not good for preserving the best quality of the final embeddings that actually lives on.
        npz_clause_path = entries_CLAUSE_EMBED_FILE.replace(".json", ".npz")
        if Path(npz_clause_path).exists():
            clause_dump = dict(np.load(npz_clause_path, allow_pickle=False))
        else:
            clause_dump = {}

        clause_dump[sha8] = np.stack(clause_embeddings)
        np.savez_compressed(npz_clause_path, **clause_dump)
        """

    report_progress()  # 7 / total_steps

    # ---------------- CENTROID / PRECENTROID ASSIGNMENT ----------------
    applied = await entry_membership_sequencer.link_entry(entry["entry_id"])

    if applied:
        # Sort defensively by similarity descending (link_entry already does this,
        # but we do not assume ordering across future changes)
        applied_sorted = sorted(applied, key=lambda x: (-x[1], x[0]))

        centroid_links = []
        precentroid_link = None

        for cid, similarity in applied_sorted:
            if cid.startswith("precentroid_"):
                # Only allow a single precentroid per entry
                if precentroid_link is None:
                    precentroid_link = {
                        "centroid_id": cid,
                        "similarity": similarity
                    }
            else:
                centroid_links.append({
                    "centroid_id": cid,
                    "similarity": similarity
                })

        # Centroids take priority over precentroids
        if centroid_links:
            entry["centroids"] = centroid_links
            entry["precentroid"] = None
        else:
            entry["centroids"] = []
            entry["precentroid"] = precentroid_link
    else:
        entry["centroids"] = []
        entry["precentroid"] = None

    report_progress()  # 8 / total_steps

    # --------------------- LOGIC FOR DELETE TOKEN  ---------------------
    entries_file = "data/entries.json"
    all_entries = load_data(entries_file)
    existing_texts = {e.get("safe_text", "") for e in all_entries}

    if safe_text not in existing_texts:
        # Only generate token if safe_text is new
        delete_token = secrets.token_hex(32)
        delete_token_hash = hashlib.sha256(delete_token.encode()).hexdigest()
        entry["delete_token_hash"] = delete_token_hash
    else:
        delete_token = None  # Safe_text already exists; no token issued

    report_progress()  # 9 / total_steps

    # ---------------- RETURN ENTRY + TOKEN ---------------------
    return {**entry, "delete_token": delete_token}  # pass token to caller

# ---------------- Sync Wrapper (meaning not asynchronous) ----------------
def process_entry(text: str, user_ip: str, max_clause_words: int = 100) -> Dict[str, Any]:
    loop = asyncio.get_event_loop()
    if loop.is_running():
        # Run async safely if we're already in an event loop
        return loop.run_until_complete(process_entry_async(text, user_ip, max_clause_words))
    else:
        return asyncio.run(process_entry_async(text, user_ip, max_clause_words))