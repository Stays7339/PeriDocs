# ==========================================
# core/map/centroids.py
# Save-state: 202602172248
# ==========================================

import os
import json
import glob
import asyncio
import functools
import logging
import re
from datetime import datetime, timezone
from typing import Dict, List
import numpy as np
from numpy.linalg import norm
from core.map.ledger import IdentifierLedger
from scipy.cluster.hierarchy import linkage, fcluster
from concurrent.futures import ThreadPoolExecutor
from app.helpers.entry_similarity import (
    cosine_similarity,
    deterministic_mean,
    safe_load_embedding,
)



logger = logging.getLogger("peridocs.centroids")

DATA_DIR = os.getenv("PERIDOCS_DATA_DIR", "data")
STATE_DIR = os.path.join(DATA_DIR, "centroids")
ARCHIVE_DIR = os.path.join(DATA_DIR, "archive")
SUGGESTIONS_DIR = os.path.join(DATA_DIR, "suggestions")

# Ensure directories exist at startup
os.makedirs(STATE_DIR, exist_ok=True)
os.makedirs(SUGGESTIONS_DIR, exist_ok=True)
logger.info(f"Ensuring centroid state directory exists at {STATE_DIR}")



# ---------- models ----------

class CentroidState:
    def __init__(
        self,
        event_index: int,
        journal_ids: List[str],
        vector: np.ndarray,
        saajes: Dict[str, float] | None = None,
        metadata: Dict | None = None,
    ):
        self.event_index = event_index
        self.journal_ids = sorted(journal_ids)
        self.vector = vector
        self.saajes = saajes or {}
        self.metadata = metadata or {}

    def serialize(self) -> Dict:
        return {
            "event_index": self.event_index,
            "journal_ids": self.journal_ids,
            "vector": self.vector.tolist(),
            "saajes": self.saajes,
            "metadata": self.metadata,
        }


class Centroid:
    def __init__(self, centroid_id: str):
        self.centroid_id = centroid_id
        self.label: str | None = None
        self.nne: str | None = None
        self.states: List[CentroidState] = []

    @property
    def current(self) -> CentroidState:
        if not self.states:
            raise RuntimeError("Centroid has no states")
        return self.states[-1]

    def serialize(self) -> Dict:
        return {
            "centroid_id": self.centroid_id,
            "label": self.label,
            "nne": self.nne,
            "states": [s.serialize() for s in self.states],
        }


# ---------- centroid system ----------

class CentroidSystem:
    """
    Lifecycle interpreter. Ledger is historical spine.
    """

    def __init__(self, ledger: IdentifierLedger):
        self._ledger = ledger
        self._centroids: Dict[str, Centroid] = {}
        self._lock = asyncio.Lock()
        self._split_suggestions: Dict[str, Dict[int, Dict]] = {}  
        self._executor = ThreadPoolExecutor(max_workers=4)
        self._zero_vector_flags_file = os.path.join(DATA_DIR, "zero_vector_flags.json")


    async def _assert_ledger_ready(self) -> None:
        """
        Hard gate: ledger must be loaded and coherent before any centroid action.
        This is non-negotiable for auditability and deterministic replay.
        """
        if not await self._ledger.is_loaded():
            raise RuntimeError(
                "IdentifierLedger is not loaded. "
                "CentroidSystem cannot operate without a loaded ledger."
            )


    def _assert_event_order(self, centroid: Centroid, new_event_index: int) -> None:
        """
        Enforce strictly increasing ledger order.
        Prevents gaps, reordering, and replay corruption.
        """
        if not centroid.states:
            return

        last_index = centroid.states[-1].event_index

        if new_event_index <= last_index:
            raise RuntimeError(
                f"Ledger order violation for {centroid.centroid_id}: "
                f"new event_index {new_event_index} <= last {last_index}"
            )
    
    def _assert_prefix_matches_ledger(self, centroid_id: str) -> None:
        prefix, raw = centroid_id.split("_", 1)
        suffix = int(raw)

        state = self._ledger.get_suffix_state(suffix)

        if prefix == "centroid" and state != "approved":
            raise RuntimeError(
                f"Centroid {centroid_id} loaded with non-approved suffix"
            )

        if prefix == "precentroid" and state != "allocated":
            raise RuntimeError(
                f"Precentroid {centroid_id} loaded with invalid suffix state"
            )


    async def _assert_centroid_registered(self, centroid_id: str) -> None:
        if not await self._ledger.has_identifier(centroid_id):
            raise RuntimeError(
                f"Centroid ID {centroid_id} does not exist in ledger"
            )

    async def persist_zero_vector_flags(self):
        if hasattr(self, "_zero_vector_flags") and self._zero_vector_flags:
            with open(self._zero_vector_flags_file, "w", encoding="utf-8") as f:
                json.dump(self._zero_vector_flags, f, indent=2)


    # ----- persistence -----
    @staticmethod
    def _numeric_suffix(fname: str) -> int:
        """
        Extract the numeric suffix from a centroid filename.
        Example: "precentroid_10.json" -> 10
        """
        match = re.search(r"_(\d+)", fname)
        if not match:
            raise ValueError(f"Invalid centroid filename: {fname}")
        return int(match.group(1))


    async def load_state(self) -> None:
        await self._assert_ledger_ready()
        async with self._lock:
            self._centroids.clear()
            if not os.path.isdir(STATE_DIR):
                return
            # Sort by numeric suffix instead of lexicographic string order
            for fname in sorted(os.listdir(STATE_DIR), key=self._numeric_suffix):
                with open(os.path.join(STATE_DIR, fname), "r") as fh:
                    payload = json.load(fh)
                c = Centroid(payload["centroid_id"])
                self._assert_prefix_matches_ledger(c.centroid_id)
                c.label = payload["label"]
                c.nne = payload["nne"]
                for s in payload["states"]:
                    self._assert_event_order(c, s["event_index"])
                    c.states.append(
                        CentroidState(
                            s["event_index"],
                            s["journal_ids"],
                            np.array(s["vector"], dtype=np.float32),
                            s.get("saajes", {}),
                            metadata=s.get("metadata", {}),
                        )
                    )
                self._centroids[c.centroid_id] = c


    async def _persist(self, centroid: Centroid) -> None:
        """
        Atomic, audit-safe persistence.
        Writes to temp file, fsyncs, then replaces.
        Mirrors ledger durability guarantees.
        """
        os.makedirs(STATE_DIR, exist_ok=True)

        final_path = os.path.join(STATE_DIR, f"{centroid.centroid_id}.json")
        tmp_path = final_path + ".tmp"

        payload = centroid.serialize()

        with open(tmp_path, "w") as f:
            json.dump(payload, f, indent=2)
            f.flush()
            os.fsync(f.fileno())

        os.replace(tmp_path, final_path)

    async def create_precentroid(self, journal_ids: List[str]) -> str:
        """
        Yeild to suggest_precentroid_for_journal
        Create a new precentroid from given journal_ids.
        - Enforces SAAJE cannot exist yet
        - Adds default metadata for admin review
        """
        logger.debug(f"[CREATE_PRECENTROID] Called with journal_ids={journal_ids}")
        await self._assert_ledger_ready()
        # allocate a ledger-backed precentroid suffix
        suffix = await self._ledger.allocate_suffix(kind="precentroid")
        cid = f"precentroid_{suffix}"
        logger.debug(f"[CREATE_PRECENTROID] Allocated centroid_id={cid}")

        # prepare deterministic embedding vector
        journal_ids = sorted(journal_ids)
        vectors = [safe_load_embedding(j) for j in journal_ids]
        vector = deterministic_mean(vectors)
        logger.debug(f"[CREATE_PRECENTROID] Deterministic mean vector shape: {vector.shape if hasattr(vector,'shape') else 'scalar'}")

        # record CREATE_PRECENTROID in ledger
        event_index = await self._ledger.record_event({
            "type": "CREATE_PRECENTROID",
            "centroid_id": cid,
            "journal_ids": journal_ids,
        })
        logger.debug(f"[CREATE_PRECENTROID] Ledger event_index={event_index}")
        
        # attach default metadata for review queue
        metadata = {
            "review_status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "human_note": "",
            "human_labels": [],
        }

        
        # create centroid instance
        c = Centroid(cid)
        logger.debug(f"[CREATE_PRECENTROID] _centroids keys now: {list(self._centroids.keys())}")
        self._assert_event_order(c, event_index)
        c.states.append(CentroidState(event_index, journal_ids, vector, saajes=None, metadata=metadata))
        self._centroids[cid] = c

        # persist safely
        await self._persist(c)

        return cid


    async def approve_precentroid(self, precentroid_id: str, *, label: str, nne: str) -> str:
        """
        Approve a precentroid:
        - Ledger-backed approval
        - Converts to a full centroid
        - Archives precentroid state
        """
        await self._assert_ledger_ready()
        async with self._lock:
            c = self._centroids.pop(precentroid_id, None)
            if c is None:
                raise RuntimeError(f"Unknown precentroid {precentroid_id}")

            suffix = int(precentroid_id.split("_")[1])
            await self._ledger.approve_suffix(suffix)
            new_id = f"centroid_{suffix}"

            # assert new centroid is recognized by ledger
            await self._assert_centroid_registered(new_id)

            event_index = await self._ledger.record_event({
                "type": "APPROVE_PRECENTROID",
                "from": precentroid_id,
                "to": new_id,
                "label": label,
                "nne": nne,
            })

            c.centroid_id = new_id
            c.label = label
            c.nne = nne
            self._assert_event_order(c, event_index)

            # preserve embedding & saajes, promote metadata
            c.states.append(CentroidState(
                event_index,
                c.current.journal_ids,
                c.current.vector,
                c.current.saajes,
                metadata=c.current.metadata  # retain metadata if needed
            ))

            self._centroids[new_id] = c
            await self._persist(c)

            # archive precentroid JSON safely
            precentroid_path = os.path.join(STATE_DIR, f"{precentroid_id}.json")
            try:
                os.remove(precentroid_path)
            except FileNotFoundError:
                pass

            return new_id


    async def reject_precentroid(
        self,
        precentroid_id: str,
        *,
        similarities: List[float],
        threshold: float,
    ) -> None:
        """
        Reject a precentroid:
        - Archives its state
        - Records REJECT_PRECENTROID ledger event
        - Safely removes precentroid from runtime state and disk
        """
        await self._assert_ledger_ready()
        async with self._lock:
            c = self._centroids.pop(precentroid_id, None)
            if c is None:
                raise RuntimeError(f"Unknown precentroid {precentroid_id}")

            await self._finalize_precentroid_rejection(
                precentroid_id=precentroid_id,
                c=c,
                similarities=similarities,
                threshold=threshold,
            )

    async def burst_precentroid(
        self,
        precentroid_id: str,
        threshold: float = 0.8
    ) -> List[str]:
        """
        Burst a precentroid as a *mode of rejection*.
        Rejection is finalized only after burst results are created.

        Steps:
        - Load the precentroid and its journal vectors.
        - Record the BURST_PRECENTROID ledger event.
        - If single entry, archive immediately.
        - Otherwise, cluster journals based on cosine similarity.
        - Create new precentroids per cluster.
        - Assign stricter local similarity threshold to metadata.
        - Finalize rejection and archive burst details.
        """
        await self._assert_ledger_ready()
        async with self._lock:
            if precentroid_id not in self._centroids:
                raise RuntimeError(f"Precentroid {precentroid_id} not found")

            # Pop precentroid from runtime
            c = self._centroids.pop(precentroid_id)
            journal_ids = c.current.journal_ids

            # Load embeddings safely
            vectors = np.stack([safe_load_embedding(j) for j in journal_ids])

            # Record burst intent before mutation
            await self._ledger.record_event({
                "type": "BURST_PRECENTROID",
                "centroid_id": precentroid_id,
                "threshold": threshold,
            })

            # Single-entry precentroid → archive immediately
            if len(journal_ids) == 1:
                await self._finalize_precentroid_rejection(
                    precentroid_id=precentroid_id,
                    c=c,
                    similarities=[],
                    threshold=threshold,
                    extra_archive={
                        "note": "single entry, archived without burst"
                    },
                )
                return []

            # Cluster journals using hierarchical clustering
            Z = linkage(vectors, method="average", metric="cosine")
            clusters = fcluster(Z, t=1 - threshold, criterion="distance")

            cluster_map: Dict[int, List[str]] = {}
            for j_id, cl_id in zip(journal_ids, clusters):
                cluster_map.setdefault(cl_id, []).append(j_id)

            new_precentroids = []
            for journals in cluster_map.values():
                new_cid = await self.create_precentroid(journals)
                new_c = self._centroids[new_cid]

                # Assign stricter local threshold to metadata for audit & future review
                new_c.states[-1].metadata["min_similarity_threshold"] = threshold
                new_precentroids.append(new_cid)

            # Finalize rejection for original precentroid
            await self._finalize_precentroid_rejection(
                precentroid_id=precentroid_id,
                c=c,
                similarities=[],
                threshold=threshold,
                extra_archive={
                    "new_precentroids": new_precentroids,
                    "burst_threshold": threshold,
                },
            )

            return new_precentroids


    # ----- drift & split suggestion -----

    async def analyze_and_suggest_split(self, centroid_id: str, threshold: float) -> None:
        """
        Perform drift analysis on a centroid.

        If drift falls below threshold:
            - Record a SUGGEST_SPLIT ledger event
            - Persist an atomic suggestion artifact to disk

        This method is:
            - Deterministic
            - Ledger-backed
            - Crash-safe
            - Replay-auditable
        """

        await self._assert_ledger_ready()

        async with self._lock:
            if centroid_id not in self._centroids:
                raise RuntimeError(f"Unknown centroid {centroid_id}")

            c = self._centroids[centroid_id]
            history = c.states

            if len(history) < 2:
                return

            sims = [
                cosine_similarity(history[i - 1].vector, history[i].vector)
                for i in range(1, len(history))
            ]

            min_sim = min(sims)

            if min_sim >= threshold:
                return

            # --- Ledger event (authoritative) ---
            event_index = await self._ledger.record_event({
                "type": "SUGGEST_SPLIT",
                "centroid_id": centroid_id,
                "threshold": threshold,
                "min_similarity": min_sim,
            })

            # --- Durable artifact ---
            os.makedirs(SUGGESTIONS_DIR, exist_ok=True)

            payload = {
                "event_index": event_index,
                "centroid_id": centroid_id,
                "label": c.label,
                "nne": c.nne,
                "similarities": sims,
                "threshold": threshold,
                "min_similarity": min_sim,
            }

            final_path = os.path.join(
                SUGGESTIONS_DIR,
                f"{centroid_id}_split_{event_index}.json",
            )
            tmp_path = final_path + ".tmp"

            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
                f.flush()
                os.fsync(f.fileno())

            os.replace(tmp_path, final_path)

    
    # ----- review projection & admin utilities -----

    async def build_review_queue(self) -> list[dict]:
        """
        Build a projection of centroids and precentroids requiring human review.

        Returns:
            List of review items in dict format compatible with admin frontend.
        Notes:
            - READ-ONLY projection: does not mutate runtime state.
            - Includes both centroids and precentroids.
            - Ensures metadata defaults exist for safe UI rendering.
        """
        await self._assert_ledger_ready()

        async with self._lock:
            queue: list[dict] = []

            for centroid_id, c in self._centroids.items():
                # Defensive: ensure metadata exists
                metadata = getattr(c.current, "metadata", {})
                if not isinstance(metadata, dict):
                    metadata = {}
                    c.current.metadata = metadata  # optional: patch runtime state

                # Default review status for precentroids
                review_status = metadata.get("review_status")
                if review_status is None:
                    review_status = "pending" if centroid_id.startswith("precentroid_") else "approved"
                    metadata["review_status"] = review_status

                if review_status != "pending":
                    continue

                # Default frontend fields
                human_note = metadata.get("human_note", "")
                human_labels = metadata.get("human_labels", [])
                created_at = metadata.get("created_at") or None
                summary = metadata.get("summary") or f"{len(c.current.journal_ids)} journal(s) attached."

                queue.append({
                    "id": centroid_id,
                    "type": "precentroid" if centroid_id.startswith("precentroid_") else "centroid",
                    "summary": summary,
                    "meta": {
                        "journal_count": len(c.current.journal_ids),
                        "label": getattr(c, "label", None),
                        "nne": getattr(c, "nne", None),
                        **metadata,  # includes human_note, human_labels, created_at, etc.
                    },
                    "status": review_status,
                    "human_note": human_note,
                    "human_labels": human_labels,
                    "created_at": created_at,
                })

            # Optional: sort queue by creation time for deterministic ordering
            queue.sort(key=lambda x: x.get("created_at") or "", reverse=False)

            logger.info(f"Built review queue with {len(queue)} items.")
            return queue

    async def _load_split_suggestions(self) -> None:
        """
        Preload all split suggestion artifacts from SUGGESTIONS_DIR into memory.
        """
        self._split_suggestions.clear()
        os.makedirs(SUGGESTIONS_DIR, exist_ok=True)

        for path in sorted(glob.glob(os.path.join(SUGGESTIONS_DIR, "*.json")), key=self._numeric_suffix):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                cid = data["centroid_id"]
                idx = data["event_index"]
                self._split_suggestions.setdefault(cid, {})[idx] = data


    # Simple helper to run blocking I/O in a thread, releasing the async lock
    async def run_sync_in_thread(self, func: callable, *args, **kwargs):
        if not callable(func):
            raise TypeError(f"Expected a callable, got {type(func)}: {func}")
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, functools.partial(func, *args, **kwargs))