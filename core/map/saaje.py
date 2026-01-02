# ==========================================
# core/map/saaje.py
# save-state 202601021659 (YYYYMMDDhhmm)
# ==========================================
"""
SAAJE (Software-Auto-Added Journal Entry) assignment layer.

Responsibilities:
- Entry → centroid affiliation (many-to-many)
- Thresholded, reversible, non-destructive
- Triggered asynchronously after persistence events
- Triggered again after material centroid changes

This module NEVER:
- Computes embeddings
- Creates / mutates centroids
- Performs admin actions
- Blocks journal submission paths
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Dict, Iterable, Optional

import numpy as np
import aiofiles

from .centroids import (
    CENTROIDS,
    SAAJE_AFFILIATIONS,
    CENTROID_METADATA,
    save_state,
    _cosine_similarity,
)

logger = logging.getLogger("peridocs.saaje")
logger.setLevel(logging.INFO)
if not logger.hasHandlers():
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter("%(asctime)s - %(message)s"))
    logger.addHandler(h)


# -------------------------------------------------
# Core entry-level assignment
# -------------------------------------------------

async def assign_entry_saaje(
    *,
    journal_id: str,
    embedding: np.ndarray,
    min_similarity: float = 0.7,
) -> Dict[str, float]:
    """
    Compute centroid affiliations for a single journal entry.

    Returns:
        {centroid_id: similarity}

    Side effects:
        Updates SAAJE_AFFILIATIONS + persists state if matches found.
    """
    if embedding.shape[0] != 1024:
        raise ValueError("SAAJE embedding dim must be 1024")

    affinities: Dict[str, float] = {}

    for cid, centroid_vec in CENTROIDS.items():
        if not cid.startswith("centroid_"):
            continue
        if CENTROID_METADATA.get(cid, {}).get("status") != "approved":
            continue

        sim = _cosine_similarity(embedding, centroid_vec)
        if sim >= min_similarity:
            affinities[cid] = sim

    if not affinities:
        logger.info(f"SAAJE: {journal_id} matched no centroids")
        return {}

    SAAJE_AFFILIATIONS[journal_id] = dict(
        sorted(affinities.items(), key=lambda x: x[1], reverse=True)
    )

    await save_state()
    logger.info(
        f"SAAJE: {journal_id} → {list(SAAJE_AFFILIATIONS[journal_id].keys())}"
    )

    return SAAJE_AFFILIATIONS[journal_id]


# -------------------------------------------------
# Background task helpers (non-blocking)
# -------------------------------------------------

def spawn_saaje_for_entry(
    *,
    journal_id: str,
    embedding_list: list[float],
    min_similarity: float = 0.7,
) -> None:
    """
    Fire-and-forget SAAJE assignment.

    Safe to call from request paths.
    """
    try:
        vec = np.array(embedding_list, dtype=float)
    except Exception:
        logger.exception("Failed to cast embedding for SAAJE")
        return

    asyncio.create_task(
        assign_entry_saaje(
            journal_id=journal_id,
            embedding=vec,
            min_similarity=min_similarity,
        )
    )


# -------------------------------------------------
# Re-evaluation after centroid changes
# -------------------------------------------------

async def reassign_saaje_for_centroids(
    *,
    affected_centroid_ids: Optional[Iterable[str]] = None,
    min_similarity: float = 0.7,
) -> None:
    """
    Re-run SAAJE assignment for *existing* entries
    after a material centroid change (approval, split, burst).

    If affected_centroid_ids is None:
        Full re-evaluation.
    Else:
        Only entries previously touching those centroids.
    """
    if not SAAJE_AFFILIATIONS:
        logger.info("SAAJE reassign skipped (no existing affiliations)")
        return

    affected = set(affected_centroid_ids) if affected_centroid_ids else None

    # snapshot to avoid mutation during iteration
    journal_ids = list(SAAJE_AFFILIATIONS.keys())

    for jid in journal_ids:
        if affected:
            if not affected.intersection(SAAJE_AFFILIATIONS.get(jid, {})):
                continue

        emb = await _load_embedding_for_journal(jid)
        if emb is None:
            continue

        await assign_entry_saaje(
            journal_id=jid,
            embedding=emb,
            min_similarity=min_similarity,
        )

    logger.info("SAAJE re-evaluation complete")


# -------------------------------------------------
# Internal utilities
# -------------------------------------------------

async def _load_embedding_for_journal(journal_id: str) -> Optional[np.ndarray]:
    """
    Loads embedding from the journal embedding dump files.

    Intentionally isolated here so we can later
    swap storage backends without touching logic.
    """
    from glob import glob

    embed_files = sorted(glob("data/journals_embeddings_dump*.json"))

    for path in embed_files:
        try:
            async with aiofiles.open(path, "r", encoding="utf-8") as f:
                data = json.loads(await f.read())
            if journal_id in data:
                vec = np.array(data[journal_id], dtype=float)
                if vec.shape[0] != 1024:
                    raise ValueError("Invalid embedding dimension")
                return vec
        except Exception:
            continue

    logger.warning(f"SAAJE: embedding not found for {journal_id}")
    return None

async def reject_saaje(
    *,
    journal_id: str,
    centroid_id: str,
    similarity: float,
    reason: str | None = None,
) -> None:
    from datetime import datetime, timezone

    SAAJE_REJECTIONS.setdefault(journal_id, {})[centroid_id] = {
        "rejected_at": datetime.now(timezone.utc).isoformat(),
        "similarity_at_rejection": similarity,
        "reason": reason,
    }

    # remove active affiliation if present
    if journal_id in SAAJE_AFFILIATIONS:
        SAAJE_AFFILIATIONS[journal_id].pop(centroid_id, None)
        if not SAAJE_AFFILIATIONS[journal_id]:
            SAAJE_AFFILIATIONS.pop(journal_id)

    await save_state()
