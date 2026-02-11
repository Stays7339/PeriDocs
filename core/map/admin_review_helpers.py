# ==========================================
# app/core/map/admin_review_helpers.py
# Fully merged, save-state: 202602031426
# ==========================================

"""
Admin review helpers for PeriDocs.

This module:
- Builds the review queue from ledger/centroid state
- Coordinates human moderation actions
- Never mutates centroid state directly
- Records no independent state outside the ledger
All authority lives downstream.
"""

import asyncio
import logging
from typing import List, Dict, Any
from core.map.centroids import cosine_similarity, load_embedding
from core.map.mapping_runtime import centroid_system


logger = logging.getLogger("peridocs.admin_review")

# ---------------- Review queue cache ----------------
_review_queue_cache: List[Dict[str, Any]] = []

async def initialize_review_queue(force_reload: bool = False) -> List[Dict[str, Any]]:
    """
    Build the review queue using runtime projection only.
    """

    global _review_queue_cache

    if _review_queue_cache and not force_reload:
        return _review_queue_cache

    queue = await centroid_system.build_review_queue()

    _review_queue_cache = queue
    return queue


async def list_review_queue(status: str = "pending") -> List[Dict[str, Any]]:
    """Return the review queue filtered by status."""
    queue = await initialize_review_queue()
    return [item for item in queue if item["status"] == status]


# ---------------- Human moderation actions ----------------

async def approve_precentroid(*, precentroid_id: str, label: str, nne: str) -> str:
    """Approve a precentroid via centroid_system."""
    return await centroid_system.approve_precentroid(precentroid_id, label=label, nne=nne)


async def reject_precentroid(*, precentroid_id: str, threshold: float) -> None:
    """Reject a precentroid, computing similarity diagnostics for audit."""
    async with centroid_system._lock:
        c = centroid_system._centroids.get(precentroid_id)
        if not c:
            raise RuntimeError(f"Unknown precentroid {precentroid_id}")
        vectors = [load_embedding(j) for j in c.current.journal_ids]
        sims = [
            cosine_similarity(vectors[i], vectors[j])
            for i in range(len(vectors))
            for j in range(i + 1, len(vectors))
        ]
    await centroid_system.reject_precentroid(precentroid_id, similarities=sims, threshold=threshold)


async def burst_precentroid(*, precentroid_id: str, stricter_threshold: float) -> List[str]:
    """Human-initiated burst of a rejected precentroid."""
    return await centroid_system.burst_precentroid(precentroid_id, threshold=stricter_threshold)


async def request_centroid_split_analysis(*, centroid_id: str, threshold: float) -> None:
    """Trigger drift analysis and split suggestion."""
    await centroid_system.analyze_and_suggest_split(centroid_id, threshold)


async def remove_journal_everywhere(*, journal_id: str) -> Dict[str, List[str]]:
    """
    Remove a journal from all centroids where it is attached.
    Delegates fully to runtime authority.
    """
    return await centroid_system.remove_journal_globally(journal_id)
