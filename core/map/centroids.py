# ==========================================
# core/map/centroids.py
# Save-state: 2026-04-27T02:19:15-04:00
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
from scipy.cluster.hierarchy import linkage, fcluster
from concurrent.futures import ThreadPoolExecutor


from core.map.ledger import IdentifierLedger
from core.map.__init__ import MINIMUM_SIMILARITY_THRESHOLD, BURST_PRECENTROID_STARTING_THRESHOLD
from core.map.perist_reasoning_data import (
    create_reasoning_data_for_centroid_state,
    serialize_graph_to_turtle,
    persist_reasoning_data
)



logger = logging.getLogger(__name__)

DATA_DIR = os.getenv("PERIDOCS_DATA_DIR", "data")
ENTRIES_DIR = os.path.join(DATA_DIR, "entries")
STATE_DIR = os.path.join(DATA_DIR, "centroids")
SUGGESTIONS_DIR = os.path.join(STATE_DIR, "suggestions")
ARCHIVE_DIR = os.path.join(STATE_DIR, "archive")

# Ensure directories exist at startup
os.makedirs(STATE_DIR, exist_ok=True)
os.makedirs(SUGGESTIONS_DIR, exist_ok=True)
os.makedirs(ARCHIVE_DIR, exist_ok=True)
logger.info(f"Ensuring centroid state directory exists at {STATE_DIR}")

def deterministic_mean(vectors: List[np.ndarray]) -> np.ndarray:
    if not vectors:
        raise ValueError("Empty vector list")
    stacked = np.stack(vectors)
    return stacked.mean(axis=0)

def safe_load_embedding(entry_id: str, entry_runtime) -> np.ndarray:
    """
    Runtime-first embedding resolution.

    Order of truth:
        1. EntryWritingRuntime memory (authoritative during request)
        2. NPZ dumps (cold fallback only for startup / integrity checks)
    """

    # ----------------------------
    # 1. FAST PATH: runtime memory
    # ----------------------------
    embedding = entry_runtime._embeddings.get(entry_id)

    if embedding is not None:
        return embedding.astype(np.float32)

    # ----------------------------
    # 2. FALLBACK: disk (ONLY if runtime missed it)
    # ----------------------------

    npz_files = sorted(
        glob.glob(os.path.join(ENTRIES_DIR, "entries_mean_embeddings_dump_*.npz"))
    )

    found = None

    for f in npz_files:
        with np.load(f, allow_pickle=False) as data:
            if entry_id in data:
                if found is not None:
                    raise RuntimeError(
                        f"Duplicate embedding found across dumps for {entry_id}"
                    )
                found = data[entry_id].astype(np.float32)

    if found is None:
        raise RuntimeError(f"Embedding not found for entry_id {entry_id}")

    return found

# ---------- models ----------

class CentroidState:
    def __init__(
        self,
        event_index: int,
        entry_ids: List[str],
        vector: np.ndarray,
        metadata: Dict | None = None,
    ):
        self.event_index = event_index
        self.entry_ids = sorted(entry_ids)
        self.vector = vector
        self.metadata = metadata or {}

    def serialize(self) -> Dict:
        """
        Serialize everything except 'vector' as .tolist() or literal.
        'vector' stays as np.ndarray for .npz or can be skipped in JSON summary.
        """
        return {
            "event_index": self.event_index,
            "entry_ids": self.entry_ids,   # still human-readable
            "vector": self.vector,         # keep as ndarray
            "metadata": self.metadata,
        }

class Centroid:
    def __init__(self, centroid_id: str):
        self.centroid_id = centroid_id
        self.description_from_human_moderator: str | None = None
        self.title_from_human_moderator: str | None = None
        self.states: List[CentroidState] = []

    @property
    def current(self) -> CentroidState:
        if not self.states:
            raise RuntimeError("Centroid has no states")
        return self.states[-1]

    def serialize(self) -> Dict:
        return {
            "centroid_id": self.centroid_id,
            "description_from_human_moderator": self.description_from_human_moderator,
            "title_from_human_moderator": self.title_from_human_moderator,
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
    
    async def _check_if_identifier_is_consistent_with_ledger(self, centroid_id: str) -> None:
        """
        Validates that a loaded centroid/precentroid ID matches the authoritative
        suffix state recorded in the ledger.

        Enforces determinism during runtime initialization.

        Raises:
            RuntimeError if:
                - ID format is invalid
                - Suffix is unknown to ledger
                - State does not match expected prefix semantics
        """
        try:
            prefix, raw = centroid_id.split("_", 1)
            suffix = int(raw)
        except (ValueError, TypeError):
            raise RuntimeError(f"Invalid centroid identifier format: {centroid_id}")

        state = await self._ledger.get_suffix_state(suffix)

        if prefix == "centroid":
            if state != "approved":
                raise RuntimeError(
                    f"Centroid {centroid_id} loaded with non-approved suffix"
                )

        elif prefix == "precentroid":
            if state != "allocated":
                raise RuntimeError(
                    f"Precentroid {centroid_id} loaded with invalid suffix state"
                )

        else:
            raise RuntimeError(f"Unknown centroid prefix: {prefix}")

    async def _assert_centroid_registered(self, centroid_id: str) -> None:
        if not await self._ledger.has_identifier(centroid_id):
            raise RuntimeError(
                f"Centroid ID {centroid_id} does not exist in ledger"
            )

    async def _verify_integrity_on_startup(self) -> None:
        """
        Comprehensive startup-time integrity check for centroids, production-ready.

        Checks performed:
        1. Ledger must be loaded.
        2. In-memory centroids:
        - JSON and NPZ exist in either STATE_DIR or ARCHIVE_DIR
        - JSON 'centroid_id' matches centroid ID
        - Vectors exist and are non-zero
        - States exist
        3. Ledger → disk consistency:
        - Every issued suffix in ledger must have corresponding JSON/NPZ
            in STATE_DIR or ARCHIVE_DIR
        4. Logs all errors before raising RuntimeError
        5. Zero vectors found during checks are recorded to zero_vector_flags.json
        """

        await self._assert_ledger_ready()

        missing_files = []
        invalid_vectors = []
        empty_states = []
        mismatched_json_ids = []
        ledger_missing_on_disk = []
        self._zero_vector_flags = {}

        # --- check in-memory centroids ---
        async with self._lock:
            for cid, centroid in self._centroids.items():
                # Define candidate paths
                candidates = [
                    {
                        "json": os.path.join(STATE_DIR, f"{cid}_summary.json"),
                        "npz": os.path.join(STATE_DIR, f"{cid}.npz"),
                    },
                    {
                        "json": os.path.join(ARCHIVE_DIR, f"{cid}_summary.json"),
                        "npz": os.path.join(ARCHIVE_DIR, f"{cid}.npz"),
                    }
                ]

                # Find first location where both files exist
                found = False
                for candidate in candidates:
                    json_path = candidate["json"]
                    npz_path = candidate["npz"]
                    if os.path.exists(json_path) and os.path.exists(npz_path):
                        found = True
                        break

                if not found:
                    missing_files.append(cid)
                    continue

                # Load JSON
                try:
                    with open(json_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if data.get("centroid_id") != cid:
                        mismatched_json_ids.append(cid)
                except Exception as e:
                    mismatched_json_ids.append(cid)
                    logger.error("[_verify_integrity] Failed to read JSON %s: %s", json_path, e)
                    continue

                # Check states
                if not data.get("states"):
                    empty_states.append(cid)
                    continue

                # Check vectors
                try:
                    npz_data = np.load(npz_path)
                    for key, vec in npz_data.items():
                        if not isinstance(vec, np.ndarray) or np.all(vec == 0):
                            invalid_vectors.append(f"{cid}:{key}")
                            self._zero_vector_flags[f"{cid}:{key}"] = "zero or invalid vector"
                except Exception as e:
                    invalid_vectors.append(f"{cid}:npz_load_fail")
                    logger.error("[_verify_integrity] Failed to read NPZ %s: %s", npz_path, e)

        # --- check ledger → disk consistency ---
        ledger_snapshot = await self._ledger.snapshot()
        next_id = ledger_snapshot.get("next_centroid_id", 0)

        for suffix_str in ledger_snapshot["issued_suffixes"].keys():
            # Find all matching files in either STATE_DIR or ARCHIVE_DIR
            npz_matches = glob.glob(os.path.join(STATE_DIR, f"*_{suffix_str}.npz")) + \
                        glob.glob(os.path.join(ARCHIVE_DIR, f"*_{suffix_str}.npz"))

            json_matches = glob.glob(os.path.join(STATE_DIR, f"*_{suffix_str}_summary.json")) + \
                        glob.glob(os.path.join(ARCHIVE_DIR, f"*_{suffix_str}_summary.json"))

            if len(npz_matches) != 1 or len(json_matches) != 1:
                ledger_missing_on_disk.append({
                    "suffix": suffix_str,
                    "npz_matches": npz_matches,
                    "json_matches": json_matches,
                })

        # Also enforce no stray files beyond next_centroid_id in both dirs
        for dir_path in [STATE_DIR, ARCHIVE_DIR]:
            for path in glob.glob(os.path.join(dir_path, "*_*.npz")):
                try:
                    suffix = self._numeric_suffix(os.path.basename(path))
                    if suffix >= next_id:
                        ledger_missing_on_disk.append({
                            "unexpected_file": path,
                            "reason": "suffix exceeds next_centroid_id",
                        })
                except Exception:
                    ledger_missing_on_disk.append({
                        "unexpected_file": path,
                        "reason": "invalid filename format",
                    })

            for path in glob.glob(os.path.join(dir_path, "*_summary.json")):
                try:
                    suffix = self._numeric_suffix(os.path.basename(path))
                    if suffix >= next_id:
                        ledger_missing_on_disk.append({
                            "unexpected_file": path,
                            "reason": "suffix exceeds next_centroid_id",
                        })
                except Exception:
                    ledger_missing_on_disk.append({
                        "unexpected_file": path,
                        "reason": "invalid filename format",
                    })

        # --- aggregate errors ---
        errors = []
        if missing_files:
            errors.append(f"In-memory centroids missing JSON/NPZ: {missing_files}")
        if invalid_vectors:
            errors.append(f"Zero or invalid vectors: {invalid_vectors}")
        if empty_states:
            errors.append(f"Centroids with no states: {empty_states}")
        if mismatched_json_ids:
            errors.append(f"JSON centroid_id mismatch: {mismatched_json_ids}")
        if ledger_missing_on_disk:
            errors.append(f"Ledger has issued suffixes but disk files missing: {ledger_missing_on_disk}")

        # persist zero vector flags
        await self.perisist_flags_for_zero_vector()

        if errors:
            for err in errors:
                logger.error("[_verify_integrity] %s", err)
            raise RuntimeError("Centroid integrity check failed. See logs above.")

        logger.info("[_verify_integrity] All centroids passed startup integrity check.")
        
    async def perisist_flags_for_zero_vector(self):
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
        """
        Load all centroids and precentroids from disk into memory.

        Production-ready behavior:
        - Loads metadata from *_summary.json files.
        - Loads vectors from corresponding .npz files.
        - Handles missing .npz files gracefully (fallback to zero vector).
        - Enforces ledger checks and event order.
        """
        await self._assert_ledger_ready()
        async with self._lock:
            self._centroids.clear()
            if not os.path.isdir(STATE_DIR):
                logger.warning("[load_state] STATE_DIR %s does not exist, nothing to load.", STATE_DIR)
                return

            # Only consider *_summary.json files
            summary_files = sorted(
                [f for f in os.listdir(STATE_DIR) if f.endswith("_summary.json")],
                key=self._numeric_suffix
            )

            for fname in summary_files:
                summary_path = os.path.join(STATE_DIR, fname)
                centroid_id = fname.rsplit("_summary.json", 1)[0]
                npz_path = os.path.join(STATE_DIR, f"{centroid_id}.npz")

                # Load JSON metadata
                try:
                    with open(summary_path, "r", encoding="utf-8") as fh:
                        payload = json.load(fh)
                except (UnicodeDecodeError, json.JSONDecodeError) as e:
                    logger.error("[load_state] Failed to read JSON %s: %s", summary_path, e)
                    continue

                # Load NPZ vectors
                vectors = {}
                if os.path.isfile(npz_path):
                    try:
                        npz_data = np.load(npz_path)
                        for key in npz_data:
                            vectors[key] = npz_data[key]
                    except Exception as e:
                        logger.error("[load_state] Failed to read NPZ %s: %s", npz_path, e)
                else:
                    logger.warning("[load_state] Missing NPZ for centroid %s, using fallback zero vectors", centroid_id)

                # Reconstruct centroid
                c = Centroid(payload["centroid_id"])
                await self._check_if_identifier_is_consistent_with_ledger(c.centroid_id)
                c.description_from_human_moderator = payload.get("description_from_human_moderator")
                c.title_from_human_moderator = payload.get("title_from_human_moderator")

                for s in payload.get("states", []):
                    self._assert_event_order(c, s["event_index"])
                    entry_ids = s.get("entry_ids", [])

                    # Build vector for this state by fetching entry embeddings
                    vector_arrays = []
                    for eid in entry_ids:
                        try:
                            vec_array = safe_load_embedding(eid, data_dir=DATA_DIR)  # MODIFIED
                        except Exception:
                            logger.warning(
                                "[load_state] Missing embedding for entry_id %s in centroid %s, using zero vector",
                                eid, centroid_id
                            )
                            vec_array = np.zeros(1024, dtype=np.float32)
                        vector_arrays.append(vec_array)

                    if vector_arrays:
                        state_vector = deterministic_mean(vector_arrays)
                    else:
                        logger.warning("[load_state] State has no entry_ids in centroid %s, using zero vector", centroid_id)
                        state_vector = np.zeros(1024, dtype=np.float32)

                    # Metadata
                    metadata = s.get("metadata", {})

                    c.states.append(CentroidState(
                        s["event_index"],
                        entry_ids,
                        state_vector,
                        metadata=metadata
                    ))

                self._centroids[c.centroid_id] = c
                logger.info("[load_state] Loaded centroid %s with %d states", c.centroid_id, len(c.states))


    async def persist_centroid_data(self, centroid: Centroid) -> None:
        os.makedirs(STATE_DIR, exist_ok=True)

        npz_path = os.path.join(STATE_DIR, f"{centroid.centroid_id}.npz")
        json_path = os.path.join(STATE_DIR, f"{centroid.centroid_id}_summary.json")
        tmp_npz = npz_path.replace(".npz", ".tmp.npz")
        tmp_json = json_path + ".tmp"

        # Only store one vector per state (mean/cached)
        npz_dump = {}
        for state_idx, state in enumerate(centroid.states):
            if state.vector is None or not isinstance(state.vector, np.ndarray):
                logger.warning("[persist_centroid_data] State %d in %s has invalid vector, using zero vector", state_idx, centroid.centroid_id)
                state_vector = np.zeros(1024, dtype=np.float32)
            else:
                state_vector = state.vector

            # Use single key per state
            key = f"{centroid.centroid_id}_state{state_idx}" 
            npz_dump[key] = state_vector 

        if not npz_dump:
            logger.info("[persist_centroid_data] Centroid %s has no valid vectors, writing single zero vector", centroid.centroid_id)
            npz_dump["empty"] = np.zeros(1024, dtype=np.float32)

        # --- Save NPZ safely ---
        try:
            np.savez_compressed(tmp_npz, **npz_dump)
            if not os.path.exists(tmp_npz):
                raise RuntimeError(f"NPZ tmp file {tmp_npz} was not created!")
            os.replace(tmp_npz, npz_path)
            logger.debug("[persist_centroid_data] Saved NPZ for centroid %s at %s", centroid.centroid_id, npz_path)
        except Exception as e:
            logger.error("[persist_centroid_data] Failed to save NPZ for centroid %s: %s", centroid.centroid_id, e)
            raise

        # --- JSON summary ---
        summary_payload = centroid.serialize()
        for s_idx, s in enumerate(summary_payload["states"]):
            s["metadata"] = dict(s.get("metadata", {}))
            s["vector"] = f"{npz_path} (state_index={s_idx})"  # persist NPZ path instead of per-entry vector

        try:
            with open(tmp_json, "w", encoding="utf-8") as f:
                json.dump(summary_payload, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_json, json_path)
            logger.debug("[persist_centroid_data] Saved JSON summary for centroid %s at %s", centroid.centroid_id, json_path)
        except Exception as e:
            logger.error("[persist_centroid_data] Failed to save JSON summary for centroid %s: %s", centroid.centroid_id, e)
            raise
            
    async def create_precentroid(self, entry_ids: List[str]) -> str:
        """
        Yeild to suggest_precentroid_for_entry
        Create a new precentroid from given entry_ids.
        - Enforces SAAJE cannot exist yet
        - Adds default metadata for admin review
        """
        logger.debug(f"[CREATE_PRECENTROID] Called with entry_ids={entry_ids}")
        await self._assert_ledger_ready()
        # allocate a ledger-backed precentroid suffix
        suffix = await self._ledger.allocate_suffix(kind="precentroid")
        cid = f"precentroid_{suffix}"
        logger.debug(f"[CREATE_PRECENTROID] Allocated centroid_id={cid}")


        # --- Deduplicate while preserving first-seen order ---
        seen = set()
        entry_ids_unique = []
        for eid in entry_ids:                          
            if eid not in seen:                        
                entry_ids_unique.append(eid)           
                seen.add(eid)                          
        entry_ids = entry_ids_unique                    

        # prepare deterministic embedding vector
        vectors = [safe_load_embedding(j, self.entry_runtime) for j in entry_ids]
        vector = deterministic_mean(vectors)
        logger.debug(f"[CREATE_PRECENTROID] Deterministic mean vector shape: {vector.shape if hasattr(vector,'shape') else 'scalar'}")

        # record CREATE_PRECENTROID in ledger
        event_index = await self._ledger.record_event({
            "type": "CREATE_PRECENTROID",
            "centroid_id": cid,
            "entry_ids": entry_ids,
        })
        logger.debug(f"[CREATE_PRECENTROID] Ledger event_index={event_index}")
        
        # attach default metadata for review queue
        metadata = {
            "review_status": "pending",
            "most_recent_promotion": datetime.now(timezone.utc).isoformat(),
            "title_from_human_moderator": "",
            "description_from_human_moderator": [],
        }

        
        # create centroid instance
        c = Centroid(cid)
        logger.debug(f"[CREATE_PRECENTROID] _centroids keys now: {list(self._centroids.keys())}")
        self._assert_event_order(c, event_index)
        c.states.append(CentroidState(event_index, entry_ids, vector, metadata=metadata))
        self._centroids[cid] = c

        # persist safely
        await self.persist_centroid_data(c)

        return cid


    async def approve_precentroid(self, precentroid_id: str, *, description_from_human_moderator: str, title_from_human_moderator: str) -> str:
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
            await self._ledger.approve_suffix(suffix, kind="centroid")
            new_id = f"centroid_{suffix}"

            # assert new centroid is recognized by ledger
            await self._assert_centroid_registered(new_id)

            event_index = await self._ledger.record_event({
                "type": "APPROVE_PRECENTROID",
                "from": precentroid_id,
                "to": new_id,
                "description_from_human_moderator": description_from_human_moderator,
                "title_from_human_moderator": title_from_human_moderator,
            })

            metadata = {
                "review_status": "approved",
                "most_recent_promotion": datetime.now(timezone.utc).isoformat(),
                "title_from_human_moderator": title_from_human_moderator,
                "description_from_human_moderator": description_from_human_moderator,
            }

            c.centroid_id = new_id
            c.description_from_human_moderator = description_from_human_moderator
            c.title_from_human_moderator = title_from_human_moderator
            self._assert_event_order(c, event_index)

            # preserve embedding & promote metadata
            # Build new metadata snapshot (authoritative for this event)
            new_metadata = {
                "review_status": "approved",
                "most_recent_promotion": datetime.now(timezone.utc).isoformat(),
                "title_from_human_moderator": title_from_human_moderator,
                "description_from_human_moderator": description_from_human_moderator,
            }

            c.states.append(CentroidState(
                event_index,
                c.current.entry_ids,
                c.current.vector,
                metadata=new_metadata
            ))

            self._centroids[new_id] = c
            await self.persist_centroid_data(c)

            # ------------------------------------------------------------
            # reasoning_file projection (post-persistence, snapshot-only)
            # ------------------------------------------------------------

            reasoning_file_graph = await create_reasoning_data_for_centroid_state(
                centroid_state=c.current,
                centroid_id=new_id,
            )

            reasoning_file_turtle = serialize_graph_to_turtle(reasoning_file_graph)

            # optional: persist reasoning_file output somewhere (file/db/cache layer)
            await persist_reasoning_data(new_id, reasoning_file_turtle)
            # ------------------------------------------------------------

            logging.info("Reconcile entries metadata nomenclature start")
            # Reconcile entries.json with approved centroid
            from core.map.entry_membership_sequencer import reconcile_centroid_membership_after_approval

            await reconcile_centroid_membership_after_approval(
                centroid_suffix=str(suffix),
                event_index=event_index,
                summary_entries=[{"entry_id": eid} for eid in c.current.entry_ids]
            )

            logging.info("Archive previous centroid type 'shed skin' start")
            # archive precentroid JSON safely
            precentroid_path = os.path.join(STATE_DIR, f"{precentroid_id}_summary.json")
            try:
                os.remove(precentroid_path)
            except FileNotFoundError:
                logging.warning("File for shed precentroid could not be found, so deletion didn't take place.")

            # archive precentroid JSON safely
            precentroid_path_for_npz = os.path.join(STATE_DIR, f"{precentroid_id}.npz")
            try:
                os.remove(precentroid_path_for_npz)
            except FileNotFoundError:
                logging.warning("File for shed precentroid could not be found, so deletion didn't take place.")

            return new_id


    async def reject_precentroid(
        self,
        precentroid_id: str,
        *,
        threshold: float,
    ) -> None:
        """
        Thin wrapper / thin caller function for the rest of the process, just so that we can easily call
        this function rather than always remembering to call a specific type of function with minor variations
        """
        await self._assert_ledger_ready()
        await self.burst_precentroid(
            precentroid_id=precentroid_id,
            threshold=threshold,
        )

    async def burst_precentroid(
        self,
        precentroid_id: str,
        threshold: float = BURST_PRECENTROID_STARTING_THRESHOLD
    ) -> List[str]:
        """
        Burst a precentroid as a *mode of rejection*.
        Rejection is finalized only after burst results are created.

        Steps:
        - Load the precentroid and its entry vectors.
        - Record the BURST_PRECENTROID ledger event.
        - If single entry, archive immediately.
        - Otherwise, cluster entries based on cosine similarity.
        - Create new precentroids per cluster.
        - Assign stricter local similarity threshold to metadata.
        - Finalize rejection and archive burst details.
        """
        await self._assert_ledger_ready()
        async with self._lock:
            if precentroid_id not in self._centroids:
                raise RuntimeError(f"Precentroid {precentroid_id} not found")
            
            # **This is missing in your latest code**
            c = self._centroids.pop(precentroid_id)
            entry_ids = c.current.entry_ids

            # Load embeddings safely
            vectors = [safe_load_embedding(j, self.entry_runtime) for j in entry_ids]

            # Record burst intent before mutation
            await self._ledger.record_event({
                "type": "BURST_PRECENTROID",
                "centroid_id": precentroid_id,
                "threshold": threshold,
            })

            # Single-entry precentroid → archive immediately
            if len(entry_ids) == 1:
                await self._finalize_precentroid_rejection(
                    precentroid_id=precentroid_id,
                    c=c,
                    threshold=threshold,
                    extra_archive={
                        "note": "single entry, archived without burst"
                    },
                )
                return []

            # Cluster entries using hierarchical clustering
            Z = linkage(vectors, method="average", metric="cosine")
            clusters = fcluster(Z, t=1 - threshold, criterion="distance")

            cluster_map: Dict[int, List[str]] = {}
            for j_id, cl_id in zip(entry_ids, clusters):
                cluster_map.setdefault(cl_id, []).append(j_id)

            new_precentroids = []
            for entries in cluster_map.values():
                new_cid = await self.create_precentroid(entries)
                new_c = self._centroids[new_cid]

                # Assign stricter local threshold to metadata for audit & future review
                new_c.states[-1].metadata["min_similarity_threshold"] = threshold
                new_precentroids.append(new_cid)

            # Finalize rejection for original precentroid
            await self._finalize_precentroid_rejection(
                precentroid_id=precentroid_id,
                c=c,
                threshold=threshold,
                extra_archive={
                    "new_precentroids": new_precentroids,
                    "burst_threshold": threshold,
                },
            )

            return new_precentroids
            
    async def _finalize_precentroid_rejection(
        self,
        *,
        precentroid_id: str,
        c: Centroid,
        threshold: float,
        extra_archive: dict,
    ) -> None:
        """
        Finalize rejection of a precentroid.

        Guarantees:
        - Append terminal state with rejection metadata
        - Persist final state
        - Move files to archive
        - No reintroduction into runtime
        """

        # --- Record rejection event in ledger (distinct, explicit lifecycle event) ---
        event_index = await self._ledger.record_event({
            "type": "REJECT_PRECENTROID",
            "centroid_id": precentroid_id,
            "failed_threshold": threshold, 
            "extra_archive": extra_archive,
        })

        # --- Build final metadata snapshot ---
        # IMPORTANT: copy to avoid mutating previous state metadata
        prev_metadata = dict(c.current.metadata or {})

        rejection_metadata = {
            **prev_metadata,
            "review_status": "rejected",
            "rejection_threshold": threshold,
            **extra_archive,
        }

        # --- Append terminal state ---
        self._assert_event_order(c, event_index)

        c.states.append(CentroidState(
            event_index,
            c.current.entry_ids,
            c.current.vector,
            metadata=rejection_metadata,
        ))

        # --- Persist final state BEFORE archiving ---
        await self.persist_centroid_data(c)

        # --- Move files to archive ---

        summary_src = os.path.join(STATE_DIR, f"{precentroid_id}_summary.json")
        npz_src = os.path.join(STATE_DIR, f"{precentroid_id}.npz")

        summary_dst = os.path.join(ARCHIVE_DIR, f"{precentroid_id}_summary.json")
        npz_dst = os.path.join(ARCHIVE_DIR, f"{precentroid_id}.npz")

        if os.path.exists(summary_src):
            os.replace(summary_src, summary_dst)

        if os.path.exists(npz_src):
            os.replace(npz_src, npz_dst)

    async def add_entry_to_centroid(
        self,
        centroid_id: str,
        entry_id: str,
        similarity: float
    ) -> int:
        """
        Adds an entry to an existing centroid.  
        Recomputes centroid vector, appends a new CentroidState, and records the event.

        Raises:
            RuntimeError if centroid_id is a precentroid or entry already exists.
        """
        from core.map.entry_membership_sequencer import get_embedding_for_entry
        await self._assert_ledger_ready()
        async with self._lock:
            if centroid_id.startswith("precentroid_"):
                raise RuntimeError("Cannot attach entry to precentroid via this method")

            # fetch current centroid
            c = self._centroids[centroid_id]
            prev_state = c.current

            # skip duplicates
            if entry_id in prev_state.entry_ids:
                raise RuntimeError(f"Entry {entry_id} already exists in {centroid_id}")

            # new list of entry IDs
            new_entry_ids = sorted(prev_state.entry_ids + [entry_id])

            # recompute centroid vector
            vectors = [await get_embedding_for_entry(j) for j in new_entry_ids]
            vector = deterministic_mean(vectors)

            # update entry → similarity mapping
            entry_similarity_to_centroid = dict(getattr(prev_state, "entry_similarity_to_centroid", {}))
            entry_similarity_to_centroid[entry_id] = similarity

            # record ledger event
            event_index = await self._ledger.record_event({
                "type": "ADD_ENTRY_TO_CENTROID",
                "centroid_id": centroid_id,
                "entry_id": entry_id,
                "similarity": similarity,
            })

            self._assert_event_order(c, event_index)

            # append new state
            c.states.append(
                CentroidState(
                    event_index=event_index,
                    entry_ids=new_entry_ids,
                    vector=vector,
                    metadata={**prev_state.metadata, "entry_similarity_to_centroid": entry_similarity_to_centroid}
                )
            )

            # persist to disk
            await self.persist_centroid_data(c)
            return event_index 




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
                    c.current.metadata = metadata

                # Default review status for precentroids
                review_status = metadata.get("review_status")
                if review_status is None:
                    review_status = "pending" if centroid_id.startswith("precentroid_") else "approved"
                    metadata["review_status"] = review_status

                if review_status != "pending":
                    continue

                # Default frontend fields
                title_from_human_moderator = metadata.get("title_from_human_moderator", "")
                description_from_human_moderator = metadata.get("description_from_human_moderator", [])
                most_recent_promotion = metadata.get("most_recent_promotion") or None
                summary = metadata.get("summary") or f"{len(c.current.entry_ids)} entry(s) attached."

                queue.append({
                        "id": centroid_id,
                        "type": "precentroid" if centroid_id.startswith("precentroid_") else "centroid",
                        "summary": summary,
                        "meta": {
                            "entry_count": len(c.current.entry_ids),
                            "entry_ids": list(c.current.entry_ids),
                            "description_from_human_moderator": getattr(c, "description_from_human_moderator", None),
                            "title_from_human_moderator": getattr(c, "title_from_human_moderator", None),
                            **metadata,
                        },
                        "status": review_status,
                        "title_from_human_moderator": title_from_human_moderator,
                        "description_from_human_moderator": description_from_human_moderator,
                        "most_recent_promotion": most_recent_promotion,
                    })

            # Optional: sort queue by creation time for deterministic ordering
            queue.sort(key=lambda x: x.get("most_recent_promotion") or "", reverse=False)

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

