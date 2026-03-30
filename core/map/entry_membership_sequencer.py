# ==========================================
# core/map/entry_membership_sequencer.py
# Save-state: 2026-03-29T16:17:15-04:00
# ==========================================
"""
Entry Membership Sequencer.

This module orchestrates:
- automatic assignment of entries into centroids (link_entry)
- candidate/precentroid assignment for human review
- ledger-backed, deterministic state updates
- full auditability, full precision
- ensures entry "snobbery": once in a centroid, entry avoids precentroids
"""
import numpy as np
from typing import Dict, List, Tuple
import logging
from datetime import datetime, timezone

from app.helpers.entry_similarity import (
    cosine_similarity, 
    deterministic_mean, 
    safe_load_embedding,
)
from core.map.mapping_runtime import centroid_system
from core.map.centroids import CentroidState
from core.map.config import MINIMUM_SIMILARITY_THRESHOLD, BURST_PRECENTROID_STARTING_THRESHOLD

logger = logging.getLogger("peridocs.entry_membership_sequencer")


class CandidateDecision:
    """
    Immutable decision result for assignment.
    """
    __slots__ = ("centroid_id", "similarity")

    def __init__(self, centroid_id: str, similarity: float):
        self.centroid_id = centroid_id
        self.similarity = similarity


async def evaluate_centroid_candidates(
    entry_id: str,
    *,
    min_similarity: float,
    max_affiliations: int | None = None,
) -> List[CandidateDecision]:
    """
    Evaluate entry against all existing centroids.
    Returns list of CandidateDecision objects sorted by similarity.
    """
    entry_vec = safe_load_embedding(entry_id)
    system = centroid_system

    decisions: List[CandidateDecision] = []

    async with system._lock:
        centroids = [
            c for c in system._centroids.values()
            if not c.centroid_id.startswith("precentroid_")
        ]

    for c in centroids:
        try:
            sim = cosine_similarity(entry_vec, c.current.vector)
        except ValueError:
            system._zero_vector_flags = getattr(system, "_zero_vector_flags", [])
            system._zero_vector_flags.append({
                "entry_id": entry_id,
                "centroid_id": c.centroid_id,
                "vector": c.current.vector.tolist(),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            logger.warning(
                "Zero vector detected: entry=%s centroid=%s -- flagged for review",
                entry_id, c.centroid_id
            )
            continue

        if sim >= min_similarity:
            decisions.append(CandidateDecision(c.centroid_id, sim))

    decisions.sort(key=lambda d: (-d.similarity, d.centroid_id))

    if max_affiliations is not None:
        decisions = decisions[:max_affiliations]

    return decisions


async def link_entry(
    entry_id: str,
    *,
    min_similarity: float = MINIMUM_SIMILARITY_THRESHOLD,
    max_affiliations: int | None = None,
) -> List[Tuple[str, float]]:
    """
    Orchestrates linking an entry:
    1. Try centroids first
    2. If no centroid match, try precentroids
    3. If no precentroid match, create new precentroid
    Returns list of (centroid_id, similarity) applied
    """
    system = centroid_system
    applied: List[Tuple[str, float]] = []

    # --- Step 1: Centroids ---
    centroid_candidates = await evaluate_centroid_candidates(
        entry_id,
        min_similarity=min_similarity,
        max_affiliations=max_affiliations,
    )

    for cand in centroid_candidates:
        try:
            await system.add_saaje(cand.centroid_id, entry_id, cand.similarity)
            applied.append((cand.centroid_id, cand.similarity))
        except Exception as e:
            logger.warning(
                "Failed to link entry to centroid: centroid=%s entry=%s err=%s",
                cand.centroid_id,
                entry_id,
                e,
            )

    # If any centroid applied, respect "snobbery" rule: avoid precentroids
    if applied:
        return applied

    # --- Step 2: Precentroids ---
    precentroid_id, sim = await suggest_precentroid_for_entry(
        entry_id,
        threshold=min_similarity
    )
    if precentroid_id:
        try:
            logger.debug(
                "[LINK_ENTRY] Appending entry %s to precentroid %s",
                entry_id, precentroid_id
            )
            event_index = await system._ledger.record_event({
                "type": "LINK_CANDIDATE_PRECENTROID",
                "centroid_id": precentroid_id,
                "entry_id": entry_id,
                "similarity": sim,
            })
            logger.debug("[LINK_ENTRY] Ledger event_index=%d", event_index)

            
            c = system._centroids[precentroid_id]
            logger.debug(
                "[LINK_ENTRY] Current entry_ids in %s: %s",
                precentroid_id, c.current.entry_ids
            )

            
            # ------------------ FIX: skip duplicate append ------------------
            if entry_id in c.current.entry_ids:
                logger.debug(
                    "Entry %s already exists in precentroid %s, skipping append.",
                    entry_id, precentroid_id
                )
                applied.append((precentroid_id, sim))  # still mark as applied
                return applied  # <-- return early, do NOT append a new CentroidState
                
            seen = set()
            new_entry_ids = []
            for eid in c.current.entry_ids + [entry_id]:       
                if eid not in seen:                              
                    new_entry_ids.append(eid)                   
                    seen.add(eid)                                
                
            vectors = [safe_load_embedding(j) for j in new_entry_ids]
            vector = deterministic_mean(vectors)
            logger.debug(
                "[LINK_ENTRY] New entry_ids: %s, vector shape: %s",
                new_entry_ids, vector.shape if hasattr(vector,'shape') else 'scalar'
            )
            c.states.append(
                CentroidState(
                    event_index=event_index,
                    entry_ids=new_entry_ids,
                    vector=vector,
                    metadata=c.current.metadata.copy()
                )
            )
            logger.debug(
                "[LINK_ENTRY] Appended entry %s to precentroid %s, total states=%d",
                entry_id, precentroid_id, len(c.states)
            )
            await system._persist(c)
            logger.debug("[LINK_ENTRY] Persisted precentroid %s to disk", precentroid_id)
            
        except Exception as e:
            logger.error(
                "[LINK_ENTRY] Failed linking entry %s to precentroid %s: %s",
                entry_id, precentroid_id, e
            )
            raise  # propagate loudly

    if precentroid_id:
        applied.append((precentroid_id, sim))

    return applied


async def unlink_entry(
    entry_id: str,
    centroid_id: str,
) -> None:
    """
    Explicit removal of an entry from a centroid.
    Ledger-backed, audit-safe.
    """
    try:
        await centroid_system.remove_saaje(centroid_id, entry_id)
        logger.info("Entry %s unlinked from centroid %s", entry_id, centroid_id)
    except Exception as e:
        logger.error("Failed to unlink entry: entry=%s centroid=%s err=%s", entry_id, centroid_id, e)
        raise

async def suggest_precentroid_for_entry(entry_id: str, threshold: float = MINIMUM_SIMILARITY_THRESHOLD) -> tuple[str | None, float | None]:
    """
    Suggests an existing precentroid for the entry.
    Returns precentroid_id if matched, else None.
    Lock priority over create_precentroid.
    """
    system = centroid_system

    try:
        entry_vec = await system.run_sync_in_thread(safe_load_embedding, entry_id)

        # ---- DEBUG: print entry norm ----
        logger.debug("ENTRY:", entry_id, "NORM:", np.linalg.norm(entry_vec))

        async with system._lock:
            if not system._centroids:
                cid = await centroid_system.create_precentroid([entry_id])
                return cid, 0.0

            for c in system._centroids.values():

                # ---- DEBUG: print centroid norm ----
                centroid_norm = np.linalg.norm(c.current.vector)
                logger.debug("CENTROID:", c.centroid_id, "NORM:", centroid_norm)

                sim = cosine_similarity(entry_vec, c.current.vector)

                local_min = c.current.metadata.get("min_similarity_threshold")
                if local_min is not None and sim < local_min:
                    continue

                if sim >= threshold:
                    if c.centroid_id.startswith("precentroid_"):
                        return c.centroid_id, sim
                    else:
                        return None

            cid = await centroid_system.create_precentroid([entry_id])
            return cid, 0.0

    except Exception as e:
        logger.error("Error in suggest_precentroid_for_entry: entry=%s err=%s", entry_id, e)
        raise