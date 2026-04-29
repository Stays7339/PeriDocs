# ==========================================
# core/nlp/process_entry.py
# save-state 2026-04-27T01:51:00-04:00
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
from core.map.mapping_runtime import centroid_system, entry_runtime
from core.map import entry_membership_sequencer

from app.helpers.entry_similarity import highlight_standout_clauses
from core.reasoning.reasoning_runtime import run_reasoning


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
    steps = ["safe_text", "clause_split", "generate_embedding", "id_generation", "crisis_check", "construct_entry","persist_embedding_only_if_no_crisis","centroid_or_precentroid_linking", "ephemeral_inference_evaluator", "logic_for_delete_token"]
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
    encrypted_safe_text = encrypt_text(text)
    report_progress()  # 1 / total_steps

    # ---------------- CLAUSE SPLIT ----------------
    clauses = split_into_clauses(safe_text)
    windows = sliding_window_clauses(clauses, max_words=max_words_in_window_of_clauses)
    report_progress()  # 2 / total_steps

    # ---------------- GENERATE EMBEDDING ----------------
    clause_embeddings = await get_embedding_async(windows)
    
    doc_embedding = np.mean(clause_embeddings, axis=0).astype(np.float32)

    # ensure embedding exists
    if doc_embedding is None:
        logger.error("[EmbeddingError] doc_embedding is None")
        raise RuntimeError("Embedding generation returned None")

    # enforce correct type
    if not isinstance(doc_embedding, np.ndarray):
        logger.error("[EmbeddingError] invalid type=%s", type(doc_embedding))
        raise RuntimeError("Embedding is not a numpy array")

    # enforce correct dimensionality
    if doc_embedding.shape != (EMBEDDING_DIM,):
        logger.error("[EmbeddingError] invalid shape=%s", doc_embedding.shape)
        raise RuntimeError(f"Invalid embedding shape: {doc_embedding.shape}")

    # detect NaNs (hard failure)
    if np.isnan(doc_embedding).any():
        logger.error("[EmbeddingError] NaN detected in embedding")
        raise RuntimeError("NaN detected in embedding vector")

    # detect zero vector (INVALID STATE in new system)
    if np.all(doc_embedding == 0):
        logger.error(
            "[EmbeddingError] zero-vector detected | norm=0 | entry staging failure"
        )
        raise RuntimeError("Zero-vector embedding detected (invalid state)")

    # optional: log distribution stats for observability
    logger.debug(
        "[EmbeddingOK] norm=%.6f mean=%.6f std=%.6f",
        float(np.linalg.norm(doc_embedding)),
        float(np.mean(doc_embedding)),
        float(np.std(doc_embedding)),
    )

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
        "embedding_file": None if crisis_msg else entry_runtime.get_current_embedding_file(),
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
        await entry_runtime.set_embedding(entry_id, doc_embedding)

    report_progress()  # 7 / total_steps

    # ---------------- CENTROID / PRECENTROID ASSIGNMENT ----------------
    applied = await entry_membership_sequencer.link_entry(entry["entry_id"])

    if applied:
        # Sort defensively by similarity descending (link_entry already does this,
        # but we do not assume ordering across future changes)
        applied_sorted = sorted(applied, key=lambda x: (-x[1], x[0]))

        centroid_links = []

        for cid, similarity, event_index in applied_sorted:
            centroid_links.append({
                "centroid_id": cid,
                "similarity": similarity,
                "event_index": event_index
            })

        entry["centroids"] = centroid_links

    report_progress()  # 8 / total_steps

    # ---------------- EPHEMERAL INFERENCE EVALUATOR ----------------
    try:

        reasoning_result = await run_reasoning(entry)

        # attach but DO NOT persist to embeddings / centroid system
        entry["reasoning"] = reasoning_result

    except Exception as e:
        logger.exception("Reasoning pipeline failed; continuing without it.")
        entry["reasoning"] = None

    report_progress()  # 9 / total_steps

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
    hash_from_token_for_deleting_entries = hashlib.sha256(delete_token.encode()).hexdigest()

    # persist only the hash
    entry["hash_from_token_for_deleting_entries"] = hash_from_token_for_deleting_entries

    report_progress()  # 10 / total_steps

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