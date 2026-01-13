# ==========================================
# core/map/admin_review_helpers.py
# Save-state: 2026011342
# ==========================================

"""
Human moderation helpers.

This module:
- coordinates review actions
- invokes CentroidSystem lifecycle transitions
- never mutates centroid state directly
- records no independent state outside the ledger

All authority lives downstream.
"""

from typing import List, Dict
import logging

#from core.map.runtime import centroid_system
from core.map.centroids import cosine_similarity, load_embedding

logger = logging.getLogger("peridocs.admin_review")


async def approve_precentroid(
    *,
    precentroid_id: str,
    label: str,
    nne: str,
) -> str:
    """
    Human approval of a precentroid.

    Effects:
        - APPROVE_SUFFIX
        - APPROVE_PRECENTROID
    """
    return await centroid_system.approve_precentroid(
        precentroid_id,
        label=label,
        nne=nne,
    )


async def reject_precentroid(
    *,
    precentroid_id: str,
    threshold: float,
) -> None:
    """
    Human rejection of a precentroid.

    Computes similarity diagnostics for audit only.
    """
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

    await centroid_system.reject_precentroid(
        precentroid_id,
        similarities=sims,
        threshold=threshold,
    )


async def burst_precentroid(
    *,
    precentroid_id: str,
    stricter_threshold: float,
) -> List[str]:
    """
    Human-initiated burst of a rejected precentroid.

    Returns:
        New precentroid IDs created.
    """
    return await centroid_system.burst_precentroid(
        precentroid_id,
        threshold=stricter_threshold,
    )


async def request_centroid_split_analysis(
    *,
    centroid_id: str,
    threshold: float,
) -> None:
    """
    Trigger drift analysis and split suggestion.

    Emits no irreversible events.
    Writes suggestion artifact only.
    """
    await centroid_system.analyze_and_suggest_split(
        centroid_id,
        threshold,
    )


async def remove_journal_everywhere(
    *,
    journal_id: str,
) -> Dict[str, List[str]]:
    """
    GDPR-aligned helper.

    Removes a journal entry from all centroids
    where it is currently attached as a SAAJE.

    Returns:
        Mapping of centroid_id -> ["removed"]
    """
    removed: Dict[str, List[str]] = {}

    async with centroid_system._lock:
        centroids = list(centroid_system._centroids.values())

    for c in centroids:
        if journal_id in c.current.saajes:
            await centroid_system.remove_saaje(
                c.centroid_id,
                journal_id,
            )
            removed.setdefault(c.centroid_id, []).append("removed")

    return removed
