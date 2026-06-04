# ==========================================
# core/nlp/process_entry.py
# save-state 2026-06-03T14:44-04:00
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
    user_id: str | None = None,
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
    window_embeddings = await get_embedding_async(windows)
    standout_window_flags = highlight_standout_clauses(
        np.asarray(window_embeddings, dtype=np.float32),
        threshold=0.65
    )

    standout_records = []

    for idx, is_standout in enumerate(standout_window_flags):

        if not is_standout:
            continue

        standout_records.append({
            "window_index": idx,
            "window_text": windows[idx],
        })

    # -------------------------------------------------
    # CLAUSE EMBEDDING VALIDATION
    # -------------------------------------------------
    if window_embeddings is None:
        raise RuntimeError("Clause embeddings returned None")

    window_embeddings = np.asarray(window_embeddings, dtype=np.float32)

    if window_embeddings.ndim != 2:
        raise RuntimeError(
            f"Clause embeddings must be rank-2 matrix, got shape={window_embeddings.shape}"
        )

    if window_embeddings.shape[0] == 0:
        raise RuntimeError("Clause embedding matrix is empty")

    if window_embeddings.shape[1] != EMBEDDING_DIM:
        raise RuntimeError(
            f"Invalid clause embedding dimension: {window_embeddings.shape}"
        )

    if np.isnan(window_embeddings).any():
        raise RuntimeError("NaN detected in clause embeddings")

    if np.isinf(window_embeddings).any():
        raise RuntimeError("Inf detected in clause embeddings")

    zero_rows = np.all(window_embeddings == 0, axis=1)

    if np.any(zero_rows):
        raise RuntimeError(
            f"Zero-vector clause embeddings detected at rows={np.where(zero_rows)[0].tolist()}"
        )
    
    doc_embedding = np.mean(window_embeddings, axis=0).astype(np.float32)

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
        "embedding": None if crisis_msg else doc_embedding,
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
        await entry_runtime.set_runtime_bundle(
            entry["entry_id"],
            embedding=entry.get("embedding"),
            window_embeddings=window_embeddings,
            window_text=np.array(windows, dtype=str),
            standout_window_flags=np.array(standout_window_flags, dtype=bool),
        )

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

    entry["centroids"] = entry.get("centroids", [])

    return build_persisted_entry(
        entry=entry,
        user_id=user_id,
        centroids=entry.get("centroids", [])
    )


def build_persisted_entry(
    entry: dict,
    user_id: str | None,
    centroids: list[dict] | None
) -> dict:
    return {
        "entry_nickname": entry.get("entry_nickname"),
        "entry_id": entry["entry_id"],
        "timestamp": entry["timestamp"],
        "ip_hash": entry["ip_hash"],
        "user_id": user_id,

        "encrypted_raw_ip": entry["encrypted_raw_ip"],
        "encrypted_raw_text": entry["encrypted_raw_text"],

        "safe_text": entry.get("safe_text", ""),

        "crisis_flag": bool(entry.get("crisis_flag", False)),

        "hash_from_token_for_deleting_entries":
            entry.get("hash_from_token_for_deleting_entries"),

        "centroids": centroids or [],
    }

