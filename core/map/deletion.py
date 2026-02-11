# ==========================================
# core/map/deletion.py
# Save-state: 202602102007
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

from core.map.ledger import IdentifierLedger
from core.map.centroids import (
    CentroidSystem,
    deterministic_mean,
    load_embedding,
)

logger = logging.getLogger("peridocs.deletion")


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
    ):
        self._ledger = ledger
        self._centroids = centroids

    # ------------------------------------------------------------
    # SAAJE REMOVAL
    # ------------------------------------------------------------

    async def remove_saaje(
        self,
        *,
        centroid_id: str,
        journal_id: str,
    ) -> None:
        """
        Remove a journal from a specific centroid.

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

            if journal_id not in prev.saajes:
                raise RuntimeError("SAAJE not present")

            # recompute membership
            journal_ids = [j for j in prev.journal_ids if j != journal_id]

            if not journal_ids:
                raise RuntimeError(
                    f"Cannot remove last journal from centroid {centroid_id}"
                )

            vectors = [load_embedding(j) for j in journal_ids]
            vector = deterministic_mean(vectors)

            saajes = dict(prev.saajes)
            del saajes[journal_id]

            event_index = await self._ledger.record_event({
                "type": "REMOVE_SAAJE",
                "centroid_id": centroid_id,
                "journal_id": journal_id,
            })

            self._centroids._assert_event_order(c, event_index)

            c.states.append(
                type(prev)(
                    event_index,
                    sorted(journal_ids),
                    vector,
                    saajes,
                )
            )

            await self._centroids._persist(c)

    # ------------------------------------------------------------
    # GLOBAL JOURNAL REMOVAL (CENTROID LAYER)
    # ------------------------------------------------------------

    async def remove_journal_globally(
        self,
        *,
        journal_id: str,
    ) -> Dict[str, List[str]]:
        """
        Remove journal from every centroid where it exists.

        Idempotent.
        Returns affected centroids.
        """

        await self._centroids._assert_ledger_ready()

        removed: Dict[str, List[str]] = {}

        async with self._centroids._lock:
            centroids_list = list(self._centroids._centroids.values())

        for c in centroids_list:
            if journal_id in c.current.saajes:
                await self.remove_saaje(
                    centroid_id=c.centroid_id,
                    journal_id=journal_id,
                )
                removed.setdefault(c.centroid_id, []).append("removed")

        return removed

    # ------------------------------------------------------------
    # EMBEDDING FILE DELETION
    # ------------------------------------------------------------

    async def delete_embedding_from_dumps(
        self,
        *,
        journal_id: str,
        data_dir: str,
    ) -> None:
        """
        Remove embedding from all dump files.

        Atomic per-file.
        Async via thread offloading.
        Idempotent.
        """

        pattern = os.path.join(data_dir, "journals_embeddings_dump*.json")
        dump_files = sorted(glob.glob(pattern))

        async def process_file(path: str):
            def _mutate():
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                if journal_id not in data:
                    return

                del data[journal_id]

                tmp = path + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
                    f.flush()
                    os.fsync(f.fileno())

                os.replace(tmp, path)

            await asyncio.to_thread(_mutate)

        for path in dump_files:
            await process_file(path)

    # ------------------------------------------------------------
    # FULL JOURNAL DELETION ORCHESTRATION
    # ------------------------------------------------------------

    async def delete_journal(
        self,
        *,
        journal_id: str,
        data_dir: str,
        initiated_by: Optional[str] = None,
        reason: str = "user_request",
    ) -> Dict[str, List[str]]:
        """
        Canonical journal deletion sequence.

        Order:
        1. Record DELETE_JOURNAL ledger event
        2. Remove from centroids
        3. Delete embeddings from disk

        Crash-safe.
        Replay-consistent.
        """

        await self._centroids._assert_ledger_ready()

        # --- Ledger first ---
        await self._ledger.record_event({
            "type": "DELETE_JOURNAL",
            "journal_id": journal_id,
            "initiated_by": initiated_by,
            "reason": reason,
        })

        # --- Remove centroid membership ---
        affected = await self.remove_journal_globally(
            journal_id=journal_id
        )

        # --- Remove embeddings ---
        await self.delete_embedding_from_dumps(
            journal_id=journal_id,
            data_dir=data_dir,
        )

        logger.info(
            f"Journal {journal_id} deleted. Affected centroids: {list(affected.keys())}"
        )

        return affected
