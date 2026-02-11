# ==========================================
# core/map/saaje.py
# Save-state: 202602031406
# ==========================================

"""
SAAJE (Software-Auto-Added Journal Entry) helpers.

This module:
- computes similarity against existing centroids
- decides whether a journal qualifies as a SAAJE
- delegates all mutation to CentroidSystem
- emits only centroid-owned ledger events

This module owns no state.
"""

from typing import Dict, List, Tuple
import logging

from core.map.centroids import (
    cosine_similarity,
    load_embedding,
)
from core.map.mapping_runtime import centroid_system


logger = logging.getLogger("peridocs.saaje")


class SaajeDecision:
    """
    Immutable decision result.
    """
    __slots__ = ("centroid_id", "similarity")

    def __init__(self, centroid_id: str, similarity: float):
        self.centroid_id = centroid_id
        self.similarity = similarity


async def evaluate_saaje_candidates(
    journal_id: str,
    *,
    min_similarity: float,
    max_affiliations: int | None = None,
) -> List[SaajeDecision]:
    """
    Determine which existing centroids a journal entry qualifies
    to be auto-attached to as a SAAJE.

    Deterministic ordering:
    - sorted by similarity desc
    - tie-broken by centroid_id
    """
    journal_vec = load_embedding(journal_id)
    system = centroid_system

    decisions: List[SaajeDecision] = []

    # Snapshot under system lock to ensure consistency
    async with system._lock:
        centroids = list(system._centroids.values())

    for c in centroids:
        if c.centroid_id.startswith("precentroid_"):
            continue  # spec: no SAAJEs on precentroids

        sim = cosine_similarity(journal_vec, c.current.vector)
        if sim >= min_similarity:
            decisions.append(SaajeDecision(c.centroid_id, sim))

    decisions.sort(
        key=lambda d: (-d.similarity, d.centroid_id)
    )

    if max_affiliations is not None:
        decisions = decisions[:max_affiliations]

    return decisions


async def apply_saajes(
    journal_id: str,
    *,
    min_similarity: float,
    max_affiliations: int | None = None,
) -> List[Tuple[str, float]]:
    """
    Evaluate and attach SAAJEs to qualifying centroids.

    Returns:
        List of (centroid_id, similarity) applied.

    Side effects:
        - ADD_SAAJE events recorded via CentroidSystem
    """
    decisions = await evaluate_saaje_candidates(
        journal_id,
        min_similarity=min_similarity,
        max_affiliations=max_affiliations,
    )

    applied: List[Tuple[str, float]] = []

    for d in decisions:
        try:
            await centroid_system.add_saaje(
                d.centroid_id,
                journal_id,
                d.similarity,
            )
            applied.append((d.centroid_id, d.similarity))
        except Exception as e:
            logger.warning(
                "Failed to apply SAAJE: centroid=%s journal=%s err=%s",
                d.centroid_id,
                journal_id,
                e,
            )

    return applied


async def remove_saaje(
    *,
    centroid_id: str,
    journal_id: str,
) -> None:
    """
    Explicit human-driven removal of a SAAJE.

    Emits:
        REMOVE_SAAJE event via CentroidSystem
    """
    await centroid_system.remove_saaje(centroid_id, journal_id)
