# ==========================================
# app/helpers/entry_writing_runtime.py
# Save-state: 2026-05-27T16:15:50-04:00
# ==========================================
import asyncio
import copy
import json
import glob
import os
import logging
import numpy as np
from typing import List, Dict, Any
from datetime import datetime, timezone
import time
from app.helpers.json_safe import json_safe

logger = logging.getLogger(__name__)



def get_npz_window_path(base_name: str) -> str:
    now = datetime.now(timezone.utc)
    window = now.hour // 6
    timestamp = now.strftime("%Y%m%d") + f"_{window}"

    return f"data/entries/{base_name}_dump_{timestamp}.npz"

DATA_DIR = os.getenv("PERIDOCS_DATA_DIR", "data")
EMBEDDING_DIM = 1024
entries_mean_embed_file = os.path.join(DATA_DIR, "entries", "entries_mean_embeddings_dump.npz")

class EntryWritingRuntime:
    """
    Singleton-style runtime for entries.json.

    Responsibilities:
    - Hold entries.json in memory
    - Provide controlled mutation methods
    - Persist changes back to disk
    - Serialize all mutations via async lock

    Explicit non-responsibilities:
    - Does not enforce schema beyond existing structure
    - Does not infer or compute centroid data (caller provides it)
    """

    def __init__(self, ledger):
        DATA_DIR = os.getenv("PERIDOCS_DATA_DIR", "data")
        self.ledger = ledger
        self._entries_path = os.path.join(DATA_DIR, "entries", "entries.json")
        self._entries: List[Dict[str, Any]] = []
        self._embeddings: Dict[str, Any] = {}
        self._initialized: bool = False
        self._npz_path = os.path.join(DATA_DIR, "entries", "entries_mean_embeddings_dump.npz")
        self._entry_index: Dict[str, Dict[str, Any]] = {}
        self._index_for_hashed_tokens_for_deleting_entries: Dict[str, Dict[str, Any]] = {}
        # ----------------------------
        # Persistence coordination
        # ----------------------------
        self._flush_queue = asyncio.Queue()  # signals "something changed"
        self._dirty_mutation_count: int = 0

        self._max_mutations_before_flush: int = 50
        self._max_seconds_without_flush: float = 15.0
        self._last_flush_time: float = time.time()

        self._background_flush_worker = None
        self._shutdown_requested: bool = False
        logger.warning("[INIT EntryRuntime] id=%s", id(self))

    async def initialize(self) -> None:
        """
        Load entries.json into memory once.

        Safe to call multiple times; only loads on first call.
        """
        logger.info("[EntryWritingRuntime] Starting initialize()")
        logger.warning("ENTRY_RUNTIME_ID=%s", id(self))

        if self._initialized:
            return

        self._entries = self._load_entries_json_from_disk()
        self._rebuild_entry_index()
        self._load_entries_embeddings_from_disk()

        await self._verify_integrity_on_startup()

        self._background_flush_worker = asyncio.create_task(
            self._flush_worker()
        )


        self._initialized = True
        logger.info("[EntryWritingRuntime] Finished initialize()")

    async def _verify_integrity_on_startup(self) -> None:
        """
        Startup-time integrity validation for entry system.

        HARD GOAL:
            - If an entry_id appears anywhere in ledger.json,
            it MUST exist in entries.json AND all embedding stores.
            - Deleted entries STILL retain embeddings (no exceptions).
            - Missing entries or embeddings cause immediate RuntimeError.
        """

        if not await self.ledger.is_loaded():
            raise RuntimeError("Ledger is not loaded")

        # (_ledger) is used so that if integrity fails, you can trace causality directly:
        # “ledger state caused entry validation failure” 
        # rather than: “some global singleton state was inconsistent somewhere”

        # ------------------------------------------------------------
        # CONFIG PATHS
        # ------------------------------------------------------------
        entries_path = self._entries_path
        entries_dir = os.path.dirname(entries_path)
        mean_file = os.path.join(entries_dir, "entries_mean_embeddings_dump.npz")
        mean_files = os.path.join(entries_dir, "entries_mean_embeddings_dump.npz")

        # ------------------------------------------------------------
        # LOAD LEDGER SNAPSHOT
        # ------------------------------------------------------------
        ledger_snapshot = await self.ledger.snapshot()

        ledger_entry_ids = set()
        for event in ledger_snapshot.get("events", []):
            eid = event.get("entry_id")
            if eid:
                ledger_entry_ids.add(eid)

        if not ledger_entry_ids:
            logger.info("[entry_runtime] No entry_ids found in ledger snapshot.")
            return

        # ------------------------------------------------------------
        # LOAD ENTRIES.JSON
        # ------------------------------------------------------------
        if not os.path.exists(entries_path):
            raise RuntimeError(f"[entry_runtime] entries.json missing at {entries_path}")

        try:
            with open(entries_path, "r", encoding="utf-8") as f:
                entries_data = json.load(f)
        except Exception as e:
            logger.error("[entry_runtime] Failed to parse entries.json: %s", e)
            raise RuntimeError("entries.json is corrupted or unreadable")

        if not isinstance(entries_data, list):
            raise RuntimeError("entries.json must be a list of entries")

        existing_entries = set()
        for entry in entries_data:
            eid = entry.get("entry_id") or entry.get("id")
            if eid:
                existing_entries.add(eid)

        # ------------------------------------------------------------
        # CHECK 1: LEDGER ↔ ENTRIES.JSON CONSISTENCY
        # ------------------------------------------------------------
        missing_entries = []
        for eid in ledger_entry_ids:
            if eid not in existing_entries:
                missing_entries.append(eid)

        if missing_entries:
            for m in missing_entries:
                logger.error("[entry_runtime] Ledger entry missing in entries.json: %s", m)
            raise RuntimeError(
                f"Entry integrity failure: {len(missing_entries)} ledger entries missing from entries.json"
            )

        # ------------------------------------------------------------
        # DETERMINE SYSTEM STATE (cold start vs existing system)
        # ------------------------------------------------------------

        system_has_history = (
            len(ledger_entry_ids) > 0
            and len(existing_entries) > 0
        )

        # ------------------------------------------------------------
        # LOAD / REQUIRE EMBEDDING FILE BASED ON STATE
        # ------------------------------------------------------------

        if not os.path.exists(mean_file):

            if system_has_history:
                # ---- STRICT MODE: data should exist ----
                raise RuntimeError(
                    f"[entry_runtime] Missing embedding store but system has history. "
                    f"Cannot bootstrap safely: {mean_file}"
                )

            else:
                # ---- COLD START MODE: safe to initialize ----
                logger.warning(
                    "[entry_runtime] Cold start detected. Creating empty embedding store."
                )
                np.savez(mean_file, _init=True)
                mean_data = np.load(mean_file)

        else:
            # ---- NORMAL PATH ----
            mean_data = np.load(mean_file)

        try:
            mean_data = np.load(mean_file)
        except Exception as e:
            raise RuntimeError(f"[entry_runtime] Failed to load canonical embedding file: {e}")
        

        # ------------------------------------------------------------
        # BUILD ENTRY SETS (EMBEDDING TABLES)
        # ------------------------------------------------------------
        embedding_keys = set()
        invalid_embeddings = []

        for key, vec in mean_data.items():
            if not isinstance(key, str):
                raise RuntimeError(f"[entry_runtime] Invalid embedding key type: {type(key)}")

            embedding_keys.add(key)

            # ----------------------------
            # STRICT VECTOR VALIDATION
            # ----------------------------
            if vec is None:
                invalid_embeddings.append((key, "mean", "None vector"))
                continue

            if not isinstance(vec, np.ndarray):
                invalid_embeddings.append((key, "mean", "non-ndarray"))
                continue

            if vec.shape != (EMBEDDING_DIM,):
                invalid_embeddings.append((key, "mean", f"bad shape {vec.shape}"))
                continue

            if vec.size == 0:
                invalid_embeddings.append((key, "mean", "empty vector"))
                continue

            if np.all(vec == 0):
                invalid_embeddings.append((key, "mean", "zero vector"))
                continue


        # ------------------------------------------------------------
        # CHECK 2: LEDGER ↔ ENTRIES ↔ EMBEDDINGS (FULL COVERAGE CHECK)
        # ------------------------------------------------------------

        missing_from_entries = []
        missing_from_embeddings = []

        # entries.json index already built above
        for eid in ledger_entry_ids:

            # must exist in entries.json
            if eid not in existing_entries:
                missing_from_entries.append(eid)

            # must exist in embeddings
            if eid not in embedding_keys:
                missing_from_embeddings.append(eid)

        if missing_from_entries:
            for eid in missing_from_entries:
                logger.error("[entry_runtime] Missing from entries.json: %s", eid)
            raise RuntimeError(
                f"[entry_runtime] Integrity failure: {len(missing_from_entries)} ledger entries missing from entries.json"
            )

        if missing_from_embeddings:
            for eid in missing_from_embeddings:
                logger.error("[entry_runtime] Missing embedding for entry: %s", eid)
            raise RuntimeError(
                f"[entry_runtime] Integrity failure: {len(missing_from_embeddings)} entries missing embeddings"
            )

        # ------------------------------------------------------------
        # FINAL FAILURE CONDITIONS
        # ------------------------------------------------------------
        if invalid_embeddings:
            for eid, label, reason in invalid_embeddings:
                logger.error("[entry_runtime] Invalid embedding: %s | %s | %s", eid, label, reason)

            raise RuntimeError("Entry embedding integrity failure (invalid vectors detected)")
            
        # ------------------------------------------------------------
        # IF SUCCESSFUL
        # ------------------------------------------------------------
        logger.info("[entry_runtime] Full integrity passed (ledger ↔ entries ↔ embeddings fully consistent)")

    async def _flush_worker(self):
        logger.info("[EntryRuntime] Flush worker started.")
        logger.warning("ENTRY_RUNTIME_ID=%s", id(self))

        while True:
            logger.debug("[FlushWorker] heartbeat loop tick")
            try:
                try:
                    # wait for signal or timeout
                    await asyncio.wait_for(self._flush_queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    pass

                if self._shutdown_requested:
                    if self._dirty_mutation_count > 0:
                        await self._persist()
                        self._dirty_mutation_count = 0
                        self._last_flush_time = time.time()
                    break

                if self._should_flush_to_disk():
                    await self._persist()
                    self._dirty_mutation_count = 0
                    self._last_flush_time = time.time()

            except Exception as e:
                logger.exception("[EntryRuntime] Flush worker error: %s", e)
                await asyncio.sleep(0.5)

    def _should_flush_to_disk(self) -> bool:
        now = time.time()
        time_since_flush = now - self._last_flush_time

        logger.debug(
            "[FlushCheck] dirty=%d time=%f",
            self._dirty_mutation_count,
            time_since_flush
        )

        if self._dirty_mutation_count >= self._max_mutations_before_flush:
            return True

        if self._dirty_mutation_count > 0 and time_since_flush >= self._max_seconds_without_flush:
            return True

        return False

    async def _signal_flush(self) -> None:
        # lightweight wake-up signal only
        logger.debug("[FlushSignal] dirty=%d", self._dirty_mutation_count)
        logger.warning("[SIGNAL runtime id=%s dirty=%d]", id(self), self._dirty_mutation_count)
        if self._flush_queue.empty():
            await self._flush_queue.put(True)
    
    async def _request_flush_to_disk(self):
        logger.warning("ENTRY_RUNTIME_ID=%s", id(self))
        await self._persist()
        self._dirty_mutation_count = 0
        self._last_flush_time = time.time()

    async def append_entry(self, entry: Dict[str, Any]) -> None:

        if not isinstance(entry, dict):
            raise RuntimeError("Invalid entry type: must be dict")

        if entry.get("crisis_flag") is True:
            return

        if entry.get("safe_text") is None:
            return

        entry_id = entry.get("entry_id") or entry.get("id")
        if not entry_id:
            raise RuntimeError("Entry missing identifier field")

        # ----------------------------
        # immediate memory mutation
        # ----------------------------
        self._entries.append(entry)
        self._entry_index[entry_id] = entry

        token_hash = entry.get("hash_from_token_for_deleting_entries")
        if token_hash:
            self._index_for_hashed_tokens_for_deleting_entries[token_hash] = entry

        # ----------------------------
        # dirty tracking
        # ----------------------------
        self._dirty_mutation_count += 1

        # ----------------------------
        # wake flush worker (non-blocking)
        # ----------------------------
        await self._signal_flush()
        
    async def set_embedding(self, entry_id: str, embedding: np.ndarray) -> None:
        """
        Contract enforcement layer for embeddings.

        Responsibilities:
        - enforce type correctness
        - enforce canonical dtype/shape
        - enforce mathematical validity
        - guarantee runtime invariants BEFORE storage

        After this function succeeds:
        - embedding is safe for all downstream systems
        - persist() should not try to validate again
        """

        # ------------------------------------------
        # TYPE ENFORCEMENT (strict, no coercion yet)
        # ------------------------------------------
        if not isinstance(embedding, np.ndarray):
            raise RuntimeError(
                f"[EmbeddingContract] expected np.ndarray | eid={entry_id} "
                f"got={type(embedding)}"
            )

        # ------------------------------------------
        # CANONICAL CONVERSION (explicit boundary)
        # ------------------------------------------
        embedding = np.asarray(embedding, dtype=np.float32)

        # ------------------------------------------
        # SHAPE CONTRACT (system invariant)
        # ------------------------------------------
        if embedding.shape != (EMBEDDING_DIM,):
            raise RuntimeError(
                f"[EmbeddingContract] invalid shape={embedding.shape} "
                f"expected={(EMBEDDING_DIM,)} | eid={entry_id}"
            )

        # ------------------------------------------
        # NUMERIC VALIDITY CHECKS
        # ------------------------------------------
        if np.isnan(embedding).any():
            logger.error("[EmbeddingContract] NaN detected | eid=%s", entry_id)
            raise RuntimeError("Embedding contains NaN")

        if np.isinf(embedding).any():
            logger.error("[EmbeddingContract] Inf detected | eid=%s", entry_id)
            raise RuntimeError("Embedding contains Inf")

        # ------------------------------------------
        # ZERO VECTOR IS INVALID STATE
        # ------------------------------------------
        if np.all(embedding == 0):
            logger.error("[EmbeddingContract] zero-vector rejected | eid=%s", entry_id)
            raise RuntimeError("Zero-vector embedding not allowed")

        # ------------------------------------------
        # STORE CANONICALIZED RESULT (memory is now immediate, no queueing)
        # ------------------------------------------
        self._embeddings[entry_id] = embedding # direct synchronous mutation

        self._dirty_mutation_count += 1
        await self._signal_flush()

    async def _persist(self) -> None:
        """
        Deterministic snapshot persistence.

        Guarantees:
        - JSON is atomically written
        - NPZ is atomically written
        - no partial state is ever visible
        - no validation or coercion occurs here
        """
        logger.warning("[PERSIST ENTERED]")
        logger.warning("WRITING TO: %s", self._entries_path)
        # ------------------------------------------
        # Before trying to write, 
        # Double check that the filepath that the rest of the software expects actually exists.
        # ------------------------------------------
        os.makedirs(os.path.dirname(self._entries_path), exist_ok=True)
        
        # ------------------------------------------
        # JSON SNAPSHOT (source of truth)
        # ------------------------------------------
        snapshot = json_safe(copy.deepcopy(self._entries))

        json_tmp = self._entries_path + ".tmp"

        with open(json_tmp, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())

        os.replace(json_tmp, self._entries_path)

        # ------------------------------------------
        # NPZ SNAPSHOT (derived embeddings cache)
        # ------------------------------------------
        npz_path = self._npz_path
        npz_tmp = npz_path + ".tmp"

        os.makedirs(os.path.dirname(npz_path), exist_ok=True)

        embedding_snapshot = copy.deepcopy(self._embeddings)

        logging.debug(f"IN-MEMORY: {len(self._embeddings)}")

        existing = 0
        for f in glob.glob("data/entries/*.npz"):
            existing += len(np.load(f).files)

        logging.debug(f"ON-DISK TOTAL: {existing}")

        with open(npz_tmp, "wb") as f:
            np.savez_compressed(f, **embedding_snapshot)

        os.replace(npz_tmp, npz_path)

        logger.info(
            "[PersistOK] entries=%d embeddings=%d",
            len(self._entries),
            len(self._embeddings),
        )

    async def shutdown(self) -> None:
        """
        Graceful shutdown of EntryWritingRuntime.

        Guarantees:
        - Flushes all pending in-memory mutations to disk if possible
        - Signals flush worker to terminate
        - Performs final fallback persist if worker does not drain queue
        """

        logger.info("[EntryRuntime] Shutdown requested.")

        # Mark shutdown intent
        self._shutdown_requested = True

        try:
            # ------------------------------------------------------------
            # 1. Wake flush worker so it can observe shutdown flag
            # ------------------------------------------------------------
            await self._flush_queue.put(True)

            # ------------------------------------------------------------
            # 2. Wait briefly for background worker to exit cleanly
            # ------------------------------------------------------------
            if self._background_flush_worker:
                try:
                    await asyncio.wait_for(self._background_flush_worker, timeout=5.0)
                except asyncio.TimeoutError:
                    logger.warning(
                        "[EntryRuntime] Flush worker did not exit in time; forcing final persist."
                    )

            # ------------------------------------------------------------
            # 3. Final safety flush (authoritative disk write)
            # ------------------------------------------------------------
            if self._dirty_mutation_count > 0:
                logger.info(
                    "[EntryRuntime] Performing final shutdown persist | dirty_mutations=%d",
                    self._dirty_mutation_count,
                )
                await self._persist()
                self._dirty_mutation_count = 0
                self._last_flush_time = time.time()

        except Exception as e:
            logger.exception("[EntryRuntime] Shutdown encountered error: %s", e)

            # LAST-RESORT GUARANTEE: attempt persistence even on failure
            try:
                await self._persist()
            except Exception as final_err:
                logger.critical(
                    "[EntryRuntime] FINAL PERSIST FAILED DURING SHUTDOWN: %s",
                    final_err,
                )

    def _load_entries_json_from_disk(self) -> List[Dict[str, Any]]:
        """
        Strict loader used ONLY at initialization / reload.

        Differences from file_ops.load_data:
        - No silent failure
        - No implicit fallback to []
        - Raises on corruption
        """

        if not os.path.exists(self._entries_path):
            # explicit empty state allowed ONLY at boot
            return []

        try:
            with open(self._entries_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            raise RuntimeError(f"Failed to load entries.json: {e}")

        if not isinstance(data, list):
            raise RuntimeError("entries.json must be a list")

        # preserve your flatten behavior if needed
        if data and isinstance(data[0], list):
            data = [item for sublist in data for item in sublist]

        return data

    def _load_entries_embeddings_from_disk(self) -> None:
        self._embeddings = {}

        entries_dir = os.path.dirname(self._entries_path)
        mean_files = sorted(
            glob.glob(os.path.join(entries_dir, "entries_mean_embeddings_dump.npz"))
        )

        for file_path in mean_files:
            data = np.load(file_path)
            for k, v in data.items():
                self._embeddings[k] = v

    async def get_embedding(self, entry_id: str):
        """
        Safe in-memory embedding read.

        Uses same lock to avoid race conditions with writes.
        """
        return self._embeddings.get(entry_id)

    async def get_all_embeddings(self):
        return copy.deepcopy(self._embeddings)

    def get_all_entries(self) -> List[Dict[str, Any]]: 
        """ Return in-memory entries. 
        NOTE: Returns direct reference. 
        Caller must not mutate outside lock. """ 
        # --- return deep copy to protect internal state --- 
        return copy.deepcopy(self._entries) 
        # ------

    async def purge_entry_metadata(
        self,
        *,
        entry_id: str,
        token_hash: str,
    ) -> bool:
        """
        Runtime-coherent entry redaction.

        Returns:
            True  -> entry was found, stripped, and persisted
            False -> no-op (not found or nothing changed)
        """

        # memory mutation now immediate

        target = None

        for entry in self._entries:  # moved out of operation
            if (
                entry.get("hash_from_token_for_deleting_entries")
                == token_hash
            ):
                target = entry
                break

        if not target:
            logger.warning("[EntryRuntime] Entry not found during strip_entry.")
            return True

        stripped = {
            "entry_id": target.get("entry_id") or target.get("id"),
            "embedding_file": target.get("embedding_file"),
            "crisis_flag": target.get("crisis_flag"),
        }

        index = self._entries.index(target)

        self._entries[index] = stripped

        stripped_entry_id = stripped.get("entry_id") or stripped.get("id")

        self._entry_index[stripped_entry_id] = stripped

        logger.info("[EntryRuntime] Entry %s stripped.", stripped_entry_id)

        self._dirty_mutation_count += 1
        await self._signal_flush()

        return True

    def get_current_embedding_file(self) -> str:
        return self._npz_path
    
    def _rebuild_entry_index(self):
        """
        # This is a lookup cache, not a second dataset.

        # It exists only to answer one question efficiently:

        # “Given an entry_id, where is the entry?”

        # Think of it as the table of contents at the front of the notebook;

        # It does not store new information. It just points to entries already in _entries.
        # _entries is for ordered iteration lists in detail. 
        # _entry_index is for fast O(1) lookup via dicts
        # If you delete _entry_index, nothing is lost except speed.
        # If you delete _entries, everything is lost.
        # the real architectural win is that you are reducing cognitive load later, 
        # because you stop scanning lists just to answer simple identity queries.
        """
        self._entry_index = {
            (e.get("entry_id") or e.get("id")): e
            for e in self._entries
        }

        self._index_for_hashed_tokens_for_deleting_entries = {
            e.get("hash_from_token_for_deleting_entries"): e
            for e in self._entries
            if e.get("hash_from_token_for_deleting_entries")
        }

    def get_entry_by_id(self, entry_id: str):
        return self._entry_index.get(entry_id)
    
    def get_entry_by_token_hash(self, token_hash: str):
        return self._index_for_hashed_tokens_for_deleting_entries.get(token_hash)
    
    async def request_flush(self) -> None:
        await self._signal_flush()