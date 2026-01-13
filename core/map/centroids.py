# ==========================================
# core/map/centroids.py
# Save-state: 202601131342
# ==========================================

import os
import json
import glob
import asyncio
import logging
from typing import Dict, List
import numpy as np
from numpy.linalg import norm
from core.map.ledger import IdentifierLedger
from scipy.cluster.hierarchy import linkage, fcluster

logger = logging.getLogger("peridocs.centroids")

DATA_DIR = "data"
STATE_DIR = "state/centroids"
ARCHIVE_DIR = "state/archive"
SUGGESTIONS_DIR = "state/suggestions"


# ---------- utilities ----------

def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    d = norm(a) * norm(b)
    if d == 0:
        raise ValueError("Zero vector")
    return float(np.dot(a, b) / d)


def deterministic_mean(vectors: List[np.ndarray]) -> np.ndarray:
    if not vectors:
        raise ValueError("Empty vector list")
    return np.stack(vectors).mean(axis=0)


def load_embedding(journal_id: str) -> np.ndarray:
    matches = sorted(glob.glob(os.path.join(DATA_DIR, f"{journal_id}.*")))
    if len(matches) != 1:
        raise RuntimeError(f"Embedding resolution failure for {journal_id}")
    path = matches[0]
    if path.endswith(".npz"):
        data = np.load(path)
        return data["embedding"]
    with open(path, "r", encoding="utf-8") as f:
        return np.array(json.load(f)["embedding"], dtype=np.float32)


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


# ---------- system ----------

class CentroidSystem:
    """
    Lifecycle interpreter. Ledger is historical spine.
    """

    def __init__(self, ledger: IdentifierLedger):
        self._ledger = ledger
        self._centroids: Dict[str, Centroid] = {}
        self._lock = asyncio.Lock()

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



    # ----- persistence -----

    async def load_state(self) -> None:
        await self._assert_ledger_ready()
        async with self._lock:
            self._centroids.clear()
            if not os.path.isdir(STATE_DIR):
                return
            for fname in sorted(os.listdir(STATE_DIR)):
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
        await self._assert_ledger_ready()
        async with self._lock:
            suffix = await self._ledger.allocate_suffix(kind="precentroid")
            cid = f"precentroid_{suffix:011d}"

            await self._assert_centroid_registered(cid)

            # enforce precentroid cannot have SAAJEs
            journal_ids = sorted(journal_ids)
            vectors = [load_embedding(j) for j in journal_ids]
            vector = deterministic_mean(vectors)

            event_index = await self._ledger.record_event({
                "type": "CREATE_PRECENTROID",
                "centroid_id": cid,
                "journal_ids": journal_ids,
            })

            c = Centroid(cid)
            self._assert_event_order(c, event_index)
            c.states.append(CentroidState(event_index, journal_ids, vector))
            self._centroids[cid] = c
            await self._persist(c)
            return cid

    async def approve_precentroid(self, precentroid_id: str, *, label: str, nne: str) -> str:
        await self._assert_ledger_ready()
        async with self._lock:
            c = self._centroids.pop(precentroid_id)
            suffix = int(precentroid_id.split("_")[1])

            # ledger enforces approval
            await self._ledger.approve_suffix(suffix)
            new_id = f"centroid_{suffix:011d}"

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
            c.states.append(
                CentroidState(
                    event_index,
                    c.current.journal_ids,
                    c.current.vector,
                    c.current.saajes,
                )
            )

            self._centroids[new_id] = c
            await self._persist(c)
            os.remove(os.path.join(STATE_DIR, f"{precentroid_id}.json"))
            return new_id

    async def add_saaje(self, centroid_id: str, journal_id: str, similarity: float) -> None:
        await self._assert_ledger_ready()
        async with self._lock:
            if centroid_id.startswith("precentroid_"):
                raise RuntimeError("Cannot attach SAAJE to precentroid")

            c = self._centroids[centroid_id]
            prev = c.current

            if journal_id in prev.journal_ids:
                raise RuntimeError("Journal already member")

            journal_ids = sorted(prev.journal_ids + [journal_id])
            vectors = [load_embedding(j) for j in journal_ids]
            vector = deterministic_mean(vectors)

            saajes = dict(prev.saajes)
            saajes[journal_id] = similarity

            event_index = await self._ledger.record_event({
                "type": "ADD_SAAJE",
                "centroid_id": centroid_id,
                "journal_id": journal_id,
                "similarity": similarity,
            })

            self._assert_event_order(c, event_index)

            c.states.append(CentroidState(event_index, journal_ids, vector, saajes))
            await self._persist(c)
    
    async def _finalize_precentroid_rejection(
        self,
        *,
        precentroid_id: str,
        c: Centroid,
        similarities: List[float],
        threshold: float,
        extra_archive: Dict | None = None,
    ) -> None:
        """
        Canonical rejection finalizer.
        Used by both plain rejection and burst rejection.
        """
        suffix = int(precentroid_id.split("_")[1])

        await self._ledger.reject_suffix(suffix)

        event_index = await self._ledger.record_event({
            "type": "REJECT_PRECENTROID",
            "centroid_id": precentroid_id,
            "failed_threshold": threshold,
        })

        os.makedirs(ARCHIVE_DIR, exist_ok=True)

        archive = {
            "precentroid_id": precentroid_id,
            "journal_ids": c.current.journal_ids,
            "count": len(c.current.journal_ids),
            "similarities": similarities,
            "failed_threshold": threshold,
            "event_index": event_index,
        }

        if extra_archive:
            archive.update(extra_archive)

        with open(os.path.join(ARCHIVE_DIR, f"{precentroid_id}.json"), "w") as f:
            json.dump(archive, f, indent=2)

        os.remove(os.path.join(STATE_DIR, f"{precentroid_id}.json"))


    async def reject_precentroid(
        self,
        precentroid_id: str,
        *,
        similarities: List[float],
        threshold: float,
    ) -> None:
        await self._assert_ledger_ready()
        async with self._lock:
            if precentroid_id not in self._centroids:
                raise RuntimeError("Unknown precentroid")

            c = self._centroids.pop(precentroid_id)

            await self._finalize_precentroid_rejection(
                precentroid_id=precentroid_id,
                c=c,
                similarities=similarities,
                threshold=threshold,
            )


 
    async def remove_saaje(self, centroid_id: str, journal_id: str) -> None:
        await self._assert_ledger_ready()
        async with self._lock:
            c = self._centroids[centroid_id]
            prev = c.current

            if journal_id not in prev.saajes:
                raise RuntimeError("SAAJE not present")

            journal_ids = [j for j in prev.journal_ids if j != journal_id]
            vectors = [load_embedding(j) for j in journal_ids]
            vector = deterministic_mean(vectors)

            saajes = dict(prev.saajes)
            del saajes[journal_id]

            event_index = await self._ledger.record_event({
                "type": "REMOVE_SAAJE",
                "centroid_id": centroid_id,
                "journal_id": journal_id,
            })

            self._assert_event_order(c, event_index)

            c.states.append(CentroidState(event_index, journal_ids, vector, saajes))
            await self._persist(c)

    # ----- drift & split suggestion -----

    async def analyze_and_suggest_split(self, centroid_id: str, threshold: float) -> None:
        await self._assert_ledger_ready()
        c = self._centroids[centroid_id]
        history = c.states
        if len(history) < 2:
            return

        sims = [
            cosine_similarity(history[i - 1].vector, history[i].vector)
            for i in range(1, len(history))
        ]

        if min(sims) < threshold:
            os.makedirs(SUGGESTIONS_DIR, exist_ok=True)
            with open(os.path.join(SUGGESTIONS_DIR, f"{centroid_id}_split.json"), "w") as f:
                json.dump(
                    {
                        "centroid_id": centroid_id,
                        "label": c.label,
                        "nne": c.nne,
                        "similarities": sims,
                        "threshold": threshold,
                    },
                    f,
                    indent=2,
                )

    async def suggest_precentroid_for_journal(self, journal_id: str, threshold: float = 0.7) -> str | None:
        """
        Suggest creation of a new precentroid if the journal entry is semantically dissimilar to all existing centroids/precentroids.
        Returns the new precentroid_id if created, None otherwise.
        """
        await self._assert_ledger_ready()
        async with self._lock:
            journal_vec = load_embedding(journal_id)

            # stricter cohesion remembered for burst precentroids
            for c in self._centroids.values():
                local_min = c.current.metadata.get("min_similarity_threshold")

                sim = cosine_similarity(journal_vec, c.current.vector)

                if local_min is not None and sim < local_min:
                    continue

                if sim >= threshold:
                    return None


            # Compare against all current centroids and precentroids
            for c in self._centroids.values():
                sim = cosine_similarity(journal_vec, c.current.vector)
                if sim >= threshold:
                    return None  # similar enough to existing centroid/precentroid

            # Dissimilar to all → create new precentroid
            return await self.create_precentroid([journal_id])

    async def burst_precentroid(
    self,
    precentroid_id: str,
    threshold: float = 0.8
) -> List[str]:
        """
        Burst a precentroid as a *mode of rejection*.
        Rejection is finalized only after burst results are created.
        """
        await self._assert_ledger_ready()
        async with self._lock:
            if precentroid_id not in self._centroids:
                raise RuntimeError(f"Precentroid {precentroid_id} not found")

            c = self._centroids.pop(precentroid_id)
            journal_ids = c.current.journal_ids
            vectors = np.stack([load_embedding(j) for j in journal_ids])

            # record burst intent before mutation
            await self._ledger.record_event({
                "type": "BURST_PRECENTROID",
                "centroid_id": precentroid_id,
                "threshold": threshold,
            })

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

            Z = linkage(vectors, method="average", metric="cosine")
            clusters = fcluster(Z, t=1 - threshold, criterion="distance")

            cluster_map: Dict[int, List[str]] = {}
            for j_id, cl_id in zip(journal_ids, clusters):
                cluster_map.setdefault(cl_id, []).append(j_id)

            new_precentroids = []
            for journals in cluster_map.values():
                new_cid = await self.create_precentroid(journals)
                # record stricter local threshold for this semantic region
                new_c = self._centroids[new_cid]
                new_c.states[-1].metadata["min_similarity_threshold"] = threshold
                new_precentroids.append(new_cid)

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
