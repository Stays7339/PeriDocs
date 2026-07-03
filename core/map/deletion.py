# ==========================================
# core/map/deletion.py
# Save-state: 2026-07-03T10:35-04:00
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
from core.entry_orchestrator.entry_similarity import (
    deterministic_mean,
    safe_load_embedding,
)
from core.map.ledger import IdentifierLedger
from core.map.centroids import CentroidSystem
from core.entry_orchestrator.entry_runtime import EntryWritingRuntime

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
    ) -> bool:
        """
        Remove an entry from a specific centroid.

        Ledger-backed.
        Lock-coherent.
        Deterministic.

        Returns:
            True if the entry was actively unlinked.
            False if it was a no-op (entry not found in centroid).
        """
        await self._centroids._assert_ledger_ready()

        # Phase 1: Context-isolated read to check state validity and membership
        async with self._centroids._lock:
            if centroid_id not in self._centroids._centroids:
                raise RuntimeError(f"Unknown centroid {centroid_id}")

            c = self._centroids._centroids[centroid_id]
            prev = c.current

            # NO-OP CHECK (effect-based under current lock state)
            if entry_id not in prev.entry_ids:
                return False

            # Prepare tracking parameters for out-of-lock execution
            entry_ids = [j for j in prev.entry_ids if j != entry_id]
            last_vector = prev.vector
            metadata = dict(prev.metadata)

        # Phase 2: Compute math and execute heavy I/O operations outside global lock
        if entry_ids:
            vectors = [await safe_load_embedding(j, self._entry_runtime) for j in entry_ids]
            vector = deterministic_mean(vectors)
        else:
            logger.info(
                f"Final remaining plain text entry for {centroid_id} deleted in best effort to stay consistent with data privacy laws."
            )
            vector = last_vector

        # Write event to immutable ledger outside of the global lock state
        event_index = await self._ledger.record_event({
            "type": "UNLINK_ENTRY",
            "centroid_id": centroid_id,
            "entry_id": entry_id,
        })

        # Phase 3: Short-lived synchronous lock re-entry to finalize structural pointer manipulation
        async with self._centroids._lock:
            if centroid_id not in self._centroids._centroids:
                raise RuntimeError(f"Centroid {centroid_id} vanished during asynchronous unlinking.")
            
            c = self._centroids._centroids[centroid_id]
            self._centroids._assert_event_order(c, event_index)

            c.states.append(
                type(prev)(
                    event_index,
                    entry_ids,
                    vector,
                    metadata,
                )
            )

        # Phase 4: Handle database/disk structural updates safely outside global lock bounds
        await self._centroids.persist_centroid_data(c)
        return True

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
            centroids_list = list(self._centroids._centroids.values())

        for c in centroids_list:
            if entry_id in c.current.entry_ids:
                # Execution safety check: capturing the fine-grained boolean outcome prevents 
                # race conditions from contaminating your tracking dictionary output layout.
                did_unlink = await self.unlink_entry_from_centroid(
                    centroid_id=c.centroid_id,
                    entry_id=entry_id,
                )
                if did_unlink:
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

        # IMPORTANT: purge_result handles boolean evaluations correctly to avoid ghost ledger writes
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