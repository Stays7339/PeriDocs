# ==========================================
# core/map/deletion.py
# Save-state: 2026-04-28T14:49:45-04:00
# ==========================================

"""
Deletion orchestration layer.

This module:
- Owns all centroid mutation related to removal
- Is ledger-backed
- Is async-safe
- Preserves deterministic replay guarantees
- Does not allocate identifiers
"""

import os
import json
import glob
import asyncio
import logging
from typing import Dict, List, Optional
import numpy as np
from app.helpers.entry_similarity import (
    deterministic_mean,
    safe_load_embedding,
)
from core.map.ledger import IdentifierLedger
from core.map.centroids import CentroidSystem
from app.helpers.entry_writing_runtime import EntryWritingRuntime
# importing class definitions, rather than the injection itself; both are necessary; injections are further on.
# if importing is considered using vocabulary, in this case, then injections are like using an exact physical object.


logger = logging.getLogger(__name__)


class DeletionManager:
    """
    Authoritative deletion handler.

    Requires:
    - Loaded ledger
    - Existing CentroidSystem instance
    """

    def __init__(
        self,
        *,
        ledger: IdentifierLedger,
        centroids: CentroidSystem,
        entry_runtime: EntryWritingRuntime
    ):
        self._ledger = ledger
        self._centroids = centroids
        self._entry_runtime = entry_runtime
        

    
    async def unlink_entry_from_centroid(
        self,
        *,
        centroid_id: str,
        entry_id: str,
    ) -> None:
        """
        Remove an entry from a specific centroid.

        Ledger-backed.
        Lock-coherent.
        Deterministic.
        """

        await self._centroids._assert_ledger_ready()

        async with self._centroids._lock:
            if centroid_id not in self._centroids._centroids:
                raise RuntimeError(f"Unknown centroid {centroid_id}")

            c = self._centroids._centroids[centroid_id]
            prev = c.current

            # NO-OP CHECK (effect-based)
            if entry_id not in prev.entry_ids:
                return

            # recompute membership
            entry_ids = [j for j in prev.entry_ids if j != entry_id]

            last_vector = prev.vector  # preserve prior state

            if entry_ids:
                vectors = [safe_load_embedding(j) for j in entry_ids]
                vector = deterministic_mean(vectors)
            else:
                logger.info(
                    f"Final remaining plain text entry for {centroid_id} deleted in best effort to stay consistent with data privacy laws."
                )
                vector = last_vector

            metadata = dict(prev.metadata)

            event_index = await self._ledger.record_event({
                "type": "UNLINK_ENTRY",
                "centroid_id": centroid_id,
                "entry_id": entry_id,
            })

            self._centroids._assert_event_order(c, event_index)

            c.states.append(
                type(prev)(
                    event_index,
                    entry_ids,
                    vector,
                    metadata,
                )
            )

            await self._centroids.persist_centroid_data(c)

    # ------------------------------------------------------------
    # GLOBAL ENTRY REMOVAL (CENTROID LAYER)
    # ------------------------------------------------------------

    async def remove_entry_globally(
        self,
        *,
        entry_id: str,
    ) -> Dict[str, List[str]]:
        """
        Remove entry from every centroid where it exists.

        Idempotent.
        Returns affected centroids.
        """

        await self._centroids._assert_ledger_ready()

        removed: Dict[str, List[str]] = {}

        async with self._centroids._lock:
            # Take all centroids currently loaded in memory and iterates through each one.
            # It does not pre-filter, and it does not use an index.
            # It brute force checks every centroid. 
            # This is to remain compliant with data privacy laws as best as possible, 
            # even if the cenetroid assignment is buggy.
            centroids_list = list(self._centroids._centroids.values())

        for c in centroids_list:
            if entry_id in c.current.entry_ids:
                await self.unlink_entry_from_centroid(
                    centroid_id=c.centroid_id,
                    entry_id=entry_id,
                )
                removed.setdefault(c.centroid_id, []).append("removed")

        return removed

    # ------------------------------------------------------------
    # FULL ENTRY DELETION ORCHESTRATION
    # ------------------------------------------------------------

    async def delete_entry(
        self,
        *,
        entry_id: str,
        token_hash: str,
        data_dir: str,
    ) -> Dict[str, List[str]]:

        await self._centroids._assert_ledger_ready()

        # ------------------------------------------------------------
        # STEP 1: REMOVE FROM CENTROIDS
        # ------------------------------------------------------------
        affected = await self.remove_entry_globally(entry_id=entry_id)

        if not affected:
            logger.warning(
                f"[DELETE_ENTRY] No centroids contained entry {entry_id} (no-op or already missing)."
            )
        else:
            logger.info(
                f"[DELETE_ENTRY] Entry {entry_id} removed from centroids: {list(affected.keys())}"
            )

        # ------------------------------------------------------------
        # STEP 2: PURGE METADATA
        # ------------------------------------------------------------
        purge_result = await self._entry_runtime.purge_entry_metadata(
            entry_id=entry_id,
            token_hash=token_hash,
        )

        # IMPORTANT: purge_result must be a boolean for this to be meaningful
        if purge_result:
            await self._ledger.record_event({
                "type": "DELETE_ENTRY",
                "entry_id": entry_id,
            })
        else:
            logger.warning(
                f"[DELETE_ENTRY] Entry {entry_id} metadata purge did NOT complete or no-op."
            )

        return affected