# ==========================================
# core/map/deletion.py
# Save-state: 2026-04-19T16:37:10-10:00
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
from app.helpers.entry_similarity import (
    deterministic_mean,
    safe_load_embedding,
)
from core.map.centroids import CentroidSystem

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
    ):
        self._ledger = ledger
        self._centroids = centroids

    
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
        """
        Canonical entry deletion sequence.

        Order:
        1. Record DELETE_ENTRY ledger event
        2. Remove from centroids

        Crash-safe.
        Replay-consistent.
        """

        await self._centroids._assert_ledger_ready()

        # --- Remove centroid membership ---
        affected = await self.remove_entry_globally(entry_id=entry_id)
        if not affected:
            logger.info(f"No-op delete for {entry_id}")
            return {}
        if affected:
            await self._ledger.record_event({
                "type": "DELETE_entry",
                "entry_id": entry_id,
            })

        logger.info(
            f"Entry {entry_id} deleted. Affected centroids: {list(affected.keys())}"
        )

        await self._purge_entry_metadata(
            entry_id=entry_id,
            token_hash=token_hash,
            data_dir=data_dir
        )

        return affected

    async def _purge_entry_metadata(
        self,
        *,
        entry_id: str,
        token_hash: str,
        data_dir: str,
    ) -> None:
        """
        Strip a single entry down to only minimal surviving fields:
        entry_id, embedding_file, crisis_flag.
        All other fields are removed from this entry only.
        Other entries in the file are untouched.
        """

        path = os.path.join(data_dir, "entries", "entries.json")

        if not os.path.exists(path):
            # Nothing to do if the file does not exist
            return

        # --- Load all entries ---
        with open(path, "r", encoding="utf-8") as f:
            try:
                entries = json.load(f)
            except json.JSONDecodeError:
                logger.error("entries.json is corrupted, cannot purge metadata.")
                return

        if not isinstance(entries, list):
            logger.error("entries.json must contain a list of entries.")
            return

        # --- Locate the target entry ---
        target = None
        for entry in entries:
            if entry.get("delete_token_hash") == token_hash:
                target = entry
                break

        if not target:
            logger.warning("Entry with matching delete_token_hash not found during metadata purge.")
            return

        # --- Strip all fields except minimal surviving ones ---
        stripped = {
            "entry_id": target.get("entry_id") or target.get("id"),
            "embedding_file": target.get("embedding_file"),
            "crisis_flag": target.get("crisis_flag"),
        }

        # Replace the original entry with stripped version
        index = entries.index(target)
        entries[index] = stripped

        # --- Write back full entries list safely ---
        with open(path, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)

        logger.info(f"Entry {entry_id} metadata purged successfully. only minimal fields remain.")