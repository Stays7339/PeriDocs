# ==========================================
# core/nlp/process_entry.py
# save-state 2026-04-03T14:52:30-04:00
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
import logging



from .embeddings import encrypt_text, get_embedding_async
from .pii import redact_pii
from .hash_utils import full_hash
from .crisis_detector import crisis_notification_async
from .crisis_recorder import append_crisis_record
from .clause_utils import split_into_clauses, sliding_window_clauses
from core.map.mapping_runtime import centroid_system
from core.map import entry_membership_sequencer
from app.helpers.file_ops import load_data
from app.helpers.entry_similarity import highlight_standout_clauses


# ---- BACKUP / TIMESTAMPED EMBEDDINGS ----
now = datetime.now(timezone.utc)
window = now.hour // 6
BACKUP_TIMESTAMP = now.strftime("%Y%m%d") + f"_{window}"
entries_EMBED_FILE = f"data/entries/entries_mean_embeddings_dump{BACKUP_TIMESTAMP}.npz"

# Glob for existing embeddings (to validate file location / expected path)
existing_embed_files = sorted(glob("data/entries/entries_mean_embeddings_dump*.npz"))
entries_CLAUSE_EMBED_FILE = f"data/entries/entries_clause_embeddings_dump{BACKUP_TIMESTAMP}.npz"

EMBEDDING_DIM = 1024
logger = logging.getLogger(__name__)

async def process_entry_async(
    text: str,
    user_ip: str,
    max_words_in_window_of_clauses: int = 66,
    progress_callback: Callable[[float], None] | None = None
) -> Dict[str, Any]:
    if not text.strip():
        raise ValueError("Empty or whitespace-only entry.")

    timestamp = datetime.now(timezone.utc).isoformat()
    ip_hash = hashlib.sha256(user_ip.encode()).hexdigest()
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
    windows = sliding_window_clauses(clauses, max_words=max_words_in_window_of_clauses)
    report_progress()  # 2 / total_steps

    # ---------------- GENERATE EMBEDDING ----------------
    clause_embeddings = await get_embedding_async(windows)
    doc_embedding = np.mean(clause_embeddings, axis=0).astype(np.float32)
    if np.all(doc_embedding == 0) or np.isnan(doc_embedding).any():
        doc_embedding = np.zeros(EMBEDDING_DIM, dtype=np.float32)
    logger.debug("DOC EMBEDDING NORM:", np.linalg.norm(doc_embedding))

    if not clause_embeddings or any(e.size == 0 for e in clause_embeddings):
        clause_embeddings = [np.zeros(EMBEDDING_DIM, dtype=np.float32) for _ in (clause_embeddings or [0])]
        logger.warning("Empty or zero-length clause embeddings detected; using zero vector fallback.")

    # --- intra-entry standout clause flags ---
    clause_embeddings_array = np.stack(clause_embeddings) if clause_embeddings else np.zeros((1, EMBEDDING_DIM), dtype=np.float32)
    standout_flags = highlight_standout_clauses(clause_embeddings_array, threshold=0.65)

    report_progress()  # 3 / total_steps

    # ---------------- ID GENERATION ----------------
    entry_id = full_hash(safe_text)

    entry_nickname = entry_id[:12]
    
    report_progress()  # 4 / total_steps
    # ---------------- CRISIS CHECK ----------------
    crisis_msg = await crisis_notification_async(text)
    report_progress()  # 5 / total_steps

    # ---------------- CONSTRUCT ENTRY ----------------
    entry: Dict[str, Any] = {
        "entry_nickname": entry_nickname,
        "entry_id": entry_id,
        "timestamp": timestamp,
        "ip_hash": ip_hash,
        "encrypted_raw_ip": encrypted_raw_ip,
        "encrypted_raw_text": encrypted_safe_text,
        "crisis_flag": bool(crisis_msg),
        "safe_text": "" if crisis_msg else safe_text,
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
        Path("data/entries").mkdir(parents=True, exist_ok=True)

        # --- Persist document embeddings as .npz ---
        npz_path = entries_EMBED_FILE

        if Path(npz_path).exists():
            # load safely, NO pickling
            loaded = dict(np.load(npz_path, allow_pickle=False))

            # validate keys
            for k in loaded.keys():
                if not isinstance(k, str) or not all(c in "0123456789abcdef" for c in k.lower()):
                    raise RuntimeError(f"Unexpected key in NPZ dump: {k}")

            npz_dump = loaded
        else:
            npz_dump = {}

        npz_dump[entry_id] = doc_embedding
        np.savez_compressed(npz_path, **npz_dump)

        Path(entries_CLAUSE_EMBED_FILE).parent.mkdir(parents=True, exist_ok=True)
        clause_dump = dict(np.load(entries_CLAUSE_EMBED_FILE, allow_pickle=False)) if Path(entries_CLAUSE_EMBED_FILE).exists() else {}
        clause_dump[entry_id] = clause_embeddings_array
        np.savez_compressed(entries_CLAUSE_EMBED_FILE, **clause_dump)

        
        standout_path = f"data/entries/entries_standout_flags_dump{BACKUP_TIMESTAMP}.npz"
        loaded_flags = dict(np.load(standout_path, allow_pickle=False)) if Path(standout_path).exists() else {}
        loaded_flags[entry_id] = np.array(standout_flags, dtype=bool)
        np.savez_compressed(standout_path, **loaded_flags)

    report_progress()  # 7 / total_steps

    # ---------------- CENTROID / PRECENTROID ASSIGNMENT ----------------
    applied = await entry_membership_sequencer.link_entry(entry["entry_id"])

    if applied:
        # Sort defensively by similarity descending (link_entry already does this,
        # but we do not assume ordering across future changes)
        applied_sorted = sorted(applied, key=lambda x: (-x[1], x[0]))

        centroid_links = []

        for cid, similarity in applied_sorted:
            centroid_links.append({
                "centroid_id": cid,
                "similarity": similarity,
                "event_index": None  # filled later during reconciliation if needed
            })

        entry["centroids"] = centroid_links

    report_progress()  # 8 / total_steps

    # --------------------- LOGIC FOR DELETE TOKEN  ---------------------
    # generate a random secret component
    random_secret = secrets.token_hex(16)

    # compact timestamp to embed in the token
    timestamp_compact = timestamp.replace(":", "").replace("-", "")

    # construct user-visible deletion token
    delete_token = f"{entry['entry_id']}.{timestamp}.{random_secret}"  
    # This is a *permutation* not a combination!
    # It's important to remember that the ordering matters everywhere else from here for the deletion pipline downstream.
    # In other words, the deletion token that the user copies must be as follows:
    # [_insert_entry_id_here].[insert_timestamp_here].[insert_the_originally_assigned_ranomized_string_here]

    # hash stored server-side
    delete_token_hash = hashlib.sha256(delete_token.encode()).hexdigest()  # NEW

    # persist only the hash
    entry["delete_token_hash"] = delete_token_hash  # NEW

    report_progress()  # 9 / total_steps

    # ---------------- RETURN ENTRY + TOKEN ---------------------
    return {**entry, "delete_token": delete_token}  # pass token to caller

# ---------------- Sync Wrapper (meaning not asynchronous) ----------------
def process_entry(text: str, user_ip: str, max_words_in_window_of_clauses: int = 100) -> Dict[str, Any]:
    loop = asyncio.get_event_loop()
    if loop.is_running():
        # Run async safely if we're already in an event loop
        return loop.run_until_complete(process_entry_async(text, user_ip, max_words_in_window_of_clauses))
    else:
        return asyncio.run(process_entry_async(text, user_ip, max_words_in_window_of_clauses))