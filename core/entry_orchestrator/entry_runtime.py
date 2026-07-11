# ==========================================
# core/entry_orchestrator/entry_runtime.py
# Save-state: 2026-07-10T15:06-04:00
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
import secrets
from app.helpers.json_safe import json_safe

logger = logging.getLogger(__name__)



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

    For Embeddings In Particular:
    process_entry_async computes everything, 
    and THEN multiple set_*() methods store state within entry_runtime.py (this file).

    All NPZ files share one invariant:

    'key space = entry_id'

    But each file stores a different projection:

    mean_embeddings → (1024,)
    window_embeddings → (N, 1024)
    window_text → (N,) strings
    standout_window_flags → (N,) booleans
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
        self._persist_lock = asyncio.Lock()

        self._flush_queue = asyncio.Queue()  # signals "something changed"
        self._dirty_mutation_count: int = 0

        self._max_mutations_before_flush: int = 50
        self._max_seconds_without_flush: float = 15.0
        self._last_flush_time: float = time.time()

        self._background_flush_worker = None
        self._shutdown_requested: bool = False
        self._window_embeddings: Dict[str, np.ndarray] = {}
        self._window_text: Dict[str, np.ndarray] = {}
        self._standout_window_flags: Dict[str, np.ndarray] = {}

        self._window_embeddings_npz_path = os.path.join(
            DATA_DIR,
            "entries",
            "entries_window_embeddings_dump.npz"
        )

        self._window_text_npz_path = os.path.join(
            DATA_DIR,
            "entries",
            "entries_window_text_dump.npz"
        )

        self._standout_window_flags_npz_path = os.path.join(
            DATA_DIR,
            "entries",
            "entries_standout_window_flags_dump.npz"
        )
        logger.debug("[INIT EntryRuntime] id=%s", id(self))

    async def initialize(self) -> None:
        """
        Load entries.json into memory once.

        Safe to call multiple times; only loads on first call.
        """
        logger.info("[EntryWritingRuntime] Starting initialize()")
        logger.debug("ENTRY_RUNTIME_ID=%s", id(self))

        if self._initialized:
            return
        

        # ============================================================
        # INTERCEPTION BOUNDARY: Online Rehydration
        # ============================================================
        from core.mode_lock import SystemModeLock
        if SystemModeLock.resolve_operational_mode() == "DATABASE":
            try:
                from core.database import db_engine
                
                # Fetch all configurations in a single unified database trip
                db_bundle = await db_engine.load_entries_bundle()
                
                self._entries = db_bundle["entries"]
                self._embeddings = db_bundle["embeddings"]
                self._window_embeddings = db_bundle["window_embeddings"]
                self._window_text = db_bundle["window_text"]
                self._standout_window_flags = db_bundle["window_flags"]
                
                # Build index maps natively from database state
                self._rebuild_entry_index()
                
                # Validate consistency across modules (Ledger vs RAM)
                await self._verify_integrity_on_startup()
                
                self._background_flush_worker = asyncio.create_task(self._flush_worker())
                self._initialized = True
                logger.info("[EntryWritingRuntime] Online database initialization complete.")
                return # Exit early, preventing file lookups
                
            except Exception as db_err:
                logger.error("[EntryWritingRuntime] Failed database bootstrap: %s", db_err)
                if SystemModeLock.is_lock_file_present_on_disk():
                    raise db_err # Refuse file system fallback if the app is officially locked to DB mode
                logger.warning("[EntryWritingRuntime] Lock unburned. Retrying fallback to local storage files.")


        # Otherwise 

        self._entries = self._load_entries_json_from_disk()
        self._rebuild_entry_index()
        self._load_entries_embeddings_from_disk()

        await self._verify_integrity_on_startup()

        # Safely load clause/window structures for offline usage only
        self._load_window_embeddings_from_disk()
        self._load_window_text_from_disk()
        self._load_standout_window_flags_from_disk()

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
            it MUST exist in the active storage layer AND all embedding stores.
            - Deleted entries STILL retain embeddings (no exceptions).
            - Missing entries or embeddings cause immediate RuntimeError.
        """

        if not await self.ledger.is_loaded():
            raise RuntimeError("Ledger is not loaded")

        # ------------------------------------------------------------
        # CONTEXT-AWARE MODE ADAPTATION
        # ------------------------------------------------------------
        from core.mode_lock import SystemModeLock
        is_db_mode = SystemModeLock.resolve_operational_mode() == "DATABASE"
        store_label = "Database Context" if is_db_mode else "entries.json"

        entries_path = self._entries_path
        entries_dir = os.path.dirname(entries_path)
        mean_file = os.path.join(entries_dir, "entries_mean_embeddings_dump.npz")

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
        # DATA SNAPSHOT ACQUISITION
        # ------------------------------------------------------------
        if is_db_mode:
            entries_data = self._entries
        else:
            if not os.path.exists(entries_path):
                raise RuntimeError(f"[entry_runtime] entries.json missing at {entries_path}")

            try:
                with open(entries_path, "r", encoding="utf-8") as f:
                    entries_data = json.load(f)
            except Exception as e:
                logger.error("[entry_runtime] Failed to parse entries.json: %s", e)
                raise RuntimeError("entries.json is corrupted or unreadable")

        if not isinstance(entries_data, list):
            raise RuntimeError(f"{store_label} payload must be structured as a list of entries")

        existing_entries = set()
        for entry in entries_data:
            eid = entry.get("entry_id") or entry.get("id")
            if eid:
                existing_entries.add(eid)

        # ------------------------------------------------------------
        # CHECK 1: LEDGER ↔ STORAGE MEMBESHIP CONSISTENCY
        # ------------------------------------------------------------
        missing_entries = []
        for eid in ledger_entry_ids:
            if eid not in existing_entries:
                missing_entries.append(eid)

        if missing_entries:
            for m in missing_entries:
                logger.error("[entry_runtime] Ledger entry missing in %s: %s", store_label, m)
            raise RuntimeError(
                f"Entry integrity failure: {len(missing_entries)} ledger entries missing from {store_label}"
            )

        # ------------------------------------------------------------
        # DETERMINE SYSTEM HISTORY STATE
        # ------------------------------------------------------------
        system_has_history = (
            len(ledger_entry_ids) > 0
            and len(existing_entries) > 0
        )

        # ------------------------------------------------------------
        # EMBEDDING MATRIX VERIFICATION ROUTINE
        # ------------------------------------------------------------
        if is_db_mode:
            mean_data = self._embeddings
        else:
            if not os.path.exists(mean_file):
                if system_has_history:
                    raise RuntimeError(
                        f"[entry_runtime] Missing embedding store but system has history. "
                        f"Cannot bootstrap safely: {mean_file}"
                    )

                logger.debug("[entry_runtime] Cold start detected. No embedding store exists yet.")
                mean_data = {}   # in-memory empty state only
            else:
                try:
                    mean_data = np.load(mean_file)
                    mean_data = dict(mean_data)  # normalize NPZ -> dict view
                except Exception as e:
                    raise RuntimeError(
                        f"[entry_runtime] Failed to load canonical embedding file: {mean_file} | {e}"
                    )

        # ------------------------------------------------------------
        # BUILD & VALIDATE ENTRY VECTOR SPACE
        # ------------------------------------------------------------
        embedding_keys = set()
        invalid_embeddings = []

        for key, vec in mean_data.items():
            if not isinstance(key, str):
                raise RuntimeError(f"[entry_runtime] Invalid embedding key type: {type(key)}")

            embedding_keys.add(key)

            # Strict Vector Validations
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
        # CHECK 2: FULL TRACE COVERAGE (LEDGER ↔ RAM ↔ MATRIX)
        # ------------------------------------------------------------
        missing_from_entries = []
        missing_from_embeddings = []

        for eid in ledger_entry_ids:
            if eid not in existing_entries:
                missing_from_entries.append(eid)

            if eid not in embedding_keys:
                missing_from_embeddings.append(eid)

        if missing_from_entries:
            for eid in missing_from_entries:
                logger.error("[entry_runtime] Missing from %s: %s", store_label, eid)
            raise RuntimeError(
                f"[entry_runtime] Integrity failure: {len(missing_from_entries)} ledger entries missing from {store_label}"
            )

        if missing_from_embeddings:
            for eid in missing_from_embeddings:
                logger.error("[entry_runtime] Missing embedding for entry: %s", eid)
            raise RuntimeError(
                f"[entry_runtime] Integrity failure: {len(missing_from_embeddings)} entries missing embeddings"
            )

        # ------------------------------------------------------------
        # CRITICAL REJECTION HANDLER
        # ------------------------------------------------------------
        if invalid_embeddings:
            for eid, label, reason in invalid_embeddings:
                logger.error("[entry_runtime] Invalid embedding: %s | %s | %s", eid, label, reason)
            raise RuntimeError("Entry embedding integrity failure (invalid vectors detected)")
            
        logger.info(
            "[entry_runtime] Full integrity passed (ledger ↔ %s ↔ embeddings fully consistent)", 
            store_label
        )

    async def _persist_guarded(self) -> None:
        async with self._persist_lock:
            await self._persist()
            
    async def _flush_worker(self):
        logger.info("[EntryRuntime] Flush worker started.")
        logger.debug("ENTRY_RUNTIME_ID=%s", id(self))

        while True:
            # logger.debug("[FlushWorker] heartbeat loop tick")
            try:
                try:
                    # wait for signal or timeout
                    await asyncio.wait_for(self._flush_queue.get(), timeout=5.0)
                except asyncio.TimeoutError:
                    pass

                if self._shutdown_requested:
                    try:
                        # immediate final flush (no batching delay)
                        if self._dirty_mutation_count > 0:
                            await self._persist_guarded()
                            self._last_flush_time = time.time()
                    finally:
                        # ensure loop always exits immediately
                        return

                if self._should_flush_to_disk():
                    await self._persist_guarded()
                    self._last_flush_time = time.time()

            except Exception as e:
                logger.exception("[EntryRuntime] Flush worker error: %s", e)
                await asyncio.sleep(0.5)

    def _should_flush_to_disk(self) -> bool:
        now = time.time()
        time_since_flush = now - self._last_flush_time
        """
        logger.debug(
            "[FlushCheck] dirty=%d time=%f",
            self._dirty_mutation_count,
            time_since_flush
        )
        """
        if self._dirty_mutation_count >= self._max_mutations_before_flush:
            return True

        if self._dirty_mutation_count > 0:
            if time_since_flush >= self._max_seconds_without_flush:
                return True

        return False

    async def _signal_dirty_queue(self) -> None:
        # lightweight wake-up signal only. Does not actually flush.
        # logger.debug("[FlushSignal] dirty=%d", self._dirty_mutation_count)
        # logger.warning("[SIGNAL runtime id=%s dirty=%d]", id(self), self._dirty_mutation_count)
        if self._flush_queue.empty():
            await self._flush_queue.put(True)
    

    async def append_entry(self, entry: Dict[str, Any]) -> None:
        """
        Appends or updates an entry in the in-memory master state.
        In flat-file mode, tracks uniquely by entry_id.
        In database mode, tracks uniquely by hash_from_token_for_deleting_entries.
        """
        if not isinstance(entry, dict):
            raise RuntimeError("Invalid entry type: must be dict")

        if entry.get("crisis_flag") is True:
            return

        if entry.get("safe_text") is None:
            return

        entry_id = entry.get("entry_id") or entry.get("id")
        if not entry_id:
            raise RuntimeError("Entry missing identifier field")

        token_hash = entry.get("hash_from_token_for_deleting_entries")

        from core.mode_lock import SystemModeLock
        if SystemModeLock.resolve_operational_mode() == "DATABASE":
            # Database mode path: hash_from_token_for_deleting_entries is the authoritative PK
            if not token_hash:
                raise RuntimeError("Database mode requires a valid hash_from_token_for_deleting_entries")

            existing_shell = self._index_for_hashed_tokens_for_deleting_entries.get(token_hash)
            
            # Fallback: check if a vector setter generated a provisional entry shell using only entry_id
            if not existing_shell:
                existing_shell = next(
                    (e for e in self._entries 
                     if (e.get("entry_id") == entry_id or e.get("id") == entry_id) 
                     and e.get("is_provisional") is True 
                     and not e.get("hash_from_token_for_deleting_entries")), 
                    None
                )

            if existing_shell and existing_shell.get("is_provisional") is True:
                existing_shell.update(entry)
                existing_shell.pop("is_provisional", None)
                target_ref = existing_shell
            else:
                self._entries.append(entry)
                target_ref = entry

            # Update database-specific indexes
            self._index_for_hashed_tokens_for_deleting_entries[token_hash] = target_ref
            # Maintain entry_index point to coordinate incoming vector shells
            self._entry_index[entry_id] = target_ref
        else:
            # Flat-file mode track: completely isolated 1:1 legacy mapping behavior
            existing_shell = self._entry_index.get(entry_id)
            if existing_shell and existing_shell.get("is_provisional") is True:
                existing_shell.update(entry)
                existing_shell.pop("is_provisional", None)
                target_ref = existing_shell
            else:
                self._entries.append(entry)
                self._entry_index[entry_id] = entry
                target_ref = entry

            if token_hash:
                self._index_for_hashed_tokens_for_deleting_entries[token_hash] = target_ref

        self._dirty_mutation_count += 1
        await self._signal_dirty_queue()

        
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

        # --- FIX: Ensure parent record structural integrity ---
        self._ensure_provisional_shell(entry_id)

        # ------------------------------------------
        # STORE CANONICALIZED RESULT (memory is now immediate, no queueing)
        # ------------------------------------------
        self._embeddings[entry_id] = embedding # direct synchronous mutation

        self._dirty_mutation_count += 1
        await self._signal_dirty_queue()

    async def set_window_text(self, entry_id: str, windows: np.ndarray) -> None:
        self._ensure_provisional_shell(entry_id)
        windows = np.asarray(windows, dtype=str)
        self._window_text[entry_id] = windows
        self._dirty_mutation_count += 1
        await self._signal_dirty_queue()


    async def set_window_embeddings(self, entry_id: str, embeddings: np.ndarray) -> None:
        embeddings = np.asarray(embeddings, dtype=np.float32)

        if embeddings.ndim != 2:
            raise RuntimeError("clause embeddings must be 2D")

        if embeddings.shape[1] != EMBEDDING_DIM:
            raise RuntimeError("invalid embedding dim")

        self._ensure_provisional_shell(entry_id)

        self._window_embeddings[entry_id] = embeddings
        self._dirty_mutation_count += 1
        await self._signal_dirty_queue()


    async def set_standout_window_flags(self, entry_id: str, flags: np.ndarray) -> None:
        self._ensure_provisional_shell(entry_id)
        flags = np.asarray(flags, dtype=bool)
        self._standout_window_flags[entry_id] = flags
        self._dirty_mutation_count += 1
        await self._signal_dirty_queue()

    async def _persist(self) -> None:
        logger.debug("[PERSIST ENTERED]")
        logger.debug("CWD=%s PID=%s", os.getcwd(), os.getpid())

        # --- FIX: Capture exactly how many mutations are currently in memory ---
        # Since we are already inside the lock, no async context switches can happen 
        # between this line and the deepcopy statements below.
        mutations_to_deduct = self._dirty_mutation_count

        json_dir = os.path.dirname(self._entries_path)
        npz_dir = os.path.dirname(self._npz_path)

        os.makedirs(json_dir, exist_ok=True)
        os.makedirs(npz_dir, exist_ok=True)

        # ============================================================
        # STEP 1: RESOLVE THE OPERATIONAL MODE
        # ============================================================
        from core.mode_lock import SystemModeLock
        operational_mode = SystemModeLock.resolve_operational_mode()

        if operational_mode == "DATABASE":
            try:
                logger.debug("[PERSIST] System is locked to DATABASE. Extracting payloads...")
                
                # Extract the JSON snapshot safely by projecting explicitly allowed fields
                PERSISTED_FIELDS = (
                    "entry_id", 
                    "entry_nickname", 
                    "timestamp", 
                    "user_id", 
                    "safe_text", 
                    "centroids", 
                    "ip_hash", 
                    "encrypted_raw_ip", 
                    "encrypted_raw_text", 
                    "crisis_flag", 
                    "hash_from_token_for_deleting_entries"
                )
                
                # Perform a deep copy of the raw memory lists to prevent state mutation during the async await
                entries_working_copy = copy.deepcopy(self._entries)
                snapshot = []
                for entry in entries_working_copy:
                    projected_entry = {k: entry.get(k) for k in PERSISTED_FIELDS}
                    snapshot.append(projected_entry)
                
                # Safely deep-copy numpy vectors and text windows to shield background I/O from runtime mutations
                embedding_snapshot = copy.deepcopy(self._embeddings)
                window_embeddings_snapshot = copy.deepcopy(self._window_embeddings)
                window_text_snapshot = copy.deepcopy(self._window_text)
                standout_flags_snapshot = copy.deepcopy(self._standout_window_flags)
                
                # Ensure the projected JSON payload contains valid serializable structures
                snapshot = json_safe(snapshot)
                
                # --------------------------------------------------------
                # INTERFACE BOUNDARY: The Database Handshake (ACTIVE)
                # --------------------------------------------------------
                from core.database import db_engine  # Assumes db_engine exports initialized PostgresStorageEngine
                
                # We preserve entry_id as the dictionary keys here because the engine uses the 
                # snapshot metadata list to resolve the relational token hashes during loop extraction.
                await db_engine.save_entries_bundle(
                    snapshot=snapshot,
                    embedding_snapshot=embedding_snapshot,
                    window_embeddings=window_embeddings_snapshot,
                    window_text=window_text_snapshot,
                    standout_flags=standout_flags_snapshot
                )
                # --------------------------------------------------------

                # --- Successfully written to DB, safely deduct ONLY what we snapshotted ---
                self._dirty_mutation_count = max(0, self._dirty_mutation_count - mutations_to_deduct)
                
                # If the database transaction committed cleanly, lock it in!
                SystemModeLock.lock_mode_permanently()  # Burns the fuse on first success
                logger.info("[PERSIST] Central database flush completed. Bypassing disk I/O.")
                return  # Exit early! Your hard drive never has to spin up.

            except Exception as db_err:
                logger.error("[PERSIST] Database transaction failed: %s", db_err)
                
                # The Veto Safety Net:
                # If the lock file ALREADY exists on disk, the database is our ONLY true source of truth.
                # Falling back to stale local files now would corrupt your emergent clusters.
                if SystemModeLock.is_lock_file_present_on_disk():
                    logger.critical("[PERSIST] CATASTROPHIC: System is legally locked to DATABASE, but backend cluster is unreachable. Halting to prevent split-brain cluster corruption.")
                    raise db_err
                
                # If the lock file DOES NOT exist yet, this was just an initial test boot that failed.
                # We can safely drop down into your original file system code.
                logger.warning("[PERSIST] Lock file not burned yet. Falling back to local emergency files.")

        # ============================================================
        # STEP 2a: ORIGINAL LOCAL STORAGE PIPELINE (100% UNCHANGED)
        # ============================================================
        logger.debug("WRITING TO JSON: %s", self._entries_path)
        logger.debug("WRITING TO NPZ: %s", self._npz_path)
        try:
            PERSISTED_FIELDS = (
                "entry_id",
                "entry_nickname",
                "timestamp",
                "user_id",

                "safe_text",

                "centroids",

                "ip_hash",
                "encrypted_raw_ip",
                "encrypted_raw_text",

                "crisis_flag",

                "hash_from_token_for_deleting_entries",
            )

            def project(entry):
                return {k: entry.get(k) for k in PERSISTED_FIELDS}

            snapshot = json_safe([project(e) for e in copy.deepcopy(self._entries)])
            json_tmp = f"{self._entries_path}.{os.getpid()}.tmp"

            logger.debug("JSON tmp path=%s", json_tmp)

            with open(json_tmp, "w", encoding="utf-8") as f:
                json.dump(snapshot, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())

            os.replace(json_tmp, self._entries_path)

            logger.info("[PERSIST] JSON committed successfully -> %s", self._entries_path)

        except Exception as e:
            logger.exception("[PERSIST] CRITICAL: JSON write failed: %s", e)
            raise  # ONLY JSON failure should crash system

        # ------------------------------------------------------------
        # 2B. WRITE NPZ
        # ------------------------------------------------------------
        logger.debug("Calling np.savez_compressed...")

        embedding_snapshot = copy.deepcopy(self._embeddings)

        pid = os.getpid()
        tmp_path = f"{self._npz_path}.tmp.{pid}.{time.time_ns()}.npz"

        logger.debug("NPZ tmp path=%s", tmp_path)

        try:
            np.savez_compressed(tmp_path, **embedding_snapshot) # When tmp_path does NOT end in .npz, NumPy always transforms it, so it is added here
            logger.debug("np.savez_compressed returned")

            # DO NOT USE os.path.exists HERE
            if not os.path.isfile(tmp_path):
                raise RuntimeError(f"[Persist] tmp NPZ not found as file: {tmp_path}")

            # sanity check (lightweight, reliable)
            if os.path.getsize(tmp_path) == 0:
                raise RuntimeError(f"[Persist] tmp NPZ is empty: {tmp_path}")

            fd = os.open(tmp_path, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)

            committed = False
            last_err = None

            for attempt in range(5):
                try:
                    os.replace(tmp_path, self._npz_path)
                    committed = True
                    break
                except Exception as e:
                    last_err = e
                    logger.warning(
                        "[Persist] os.replace failed attempt=%d err=%s",
                        attempt + 1,
                        repr(e)
                    )
                    time.sleep(0.05 * (attempt + 1))

            if not committed:
                raise RuntimeError(f"[Persist] failed to commit NPZ after retries: {last_err}")

            # ============================================================
            # 2C. CLAUSE-LEVEL NPZ WRITES
            # ============================================================

            np.savez_compressed(
                self._window_embeddings_npz_path,
                **self._window_embeddings
            )

            np.savez_compressed(
                self._window_text_npz_path,
                **self._window_text
            )

            np.savez_compressed(
                self._standout_window_flags_npz_path,
                **self._standout_window_flags
            )

            # --- FIX: Successfully written to disk, safely deduct what we snapshotted ---
            self._dirty_mutation_count = max(0, self._dirty_mutation_count - mutations_to_deduct)

            logger.debug("NPZ commit complete -> %s", self._npz_path)

        except Exception:
            logger.exception("[Persist] NPZ write failed")
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass
            return

        
            
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
        file_path = os.path.join(entries_dir, "entries_mean_embeddings_dump.npz")

        if not os.path.exists(file_path):
            logger.warning("[NPZ LOAD] missing file, skipping: %s", file_path)
            return

        try:
            # validate before trusting
            with np.load(file_path) as data:
                for k, v in data.items():
                    if isinstance(v, np.ndarray) and v.shape == (EMBEDDING_DIM,):
                        self._embeddings[k] = v
                    else:
                        logger.warning("[NPZ LOAD] skipping invalid vector %s shape=%s", k, getattr(v, "shape", None))

        except EOFError:
            logger.error("[NPZ LOAD] corrupted NPZ (EOF), ignoring file: %s", file_path)

        except Exception as e:
            logger.error("[NPZ LOAD] unreadable NPZ: %s err=%s", file_path, e)
                    
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

    def _ensure_provisional_shell(self, entry_id: str) -> None:
        """
        Ensures a parent master row shell exists in memory before child vectors 
        or window components attempt to flush to a relational database engine.
        And we did that specifically because the database was getting called for a flush 
        the same moment connections were being made for a pre-centroid.
        """
        if entry_id not in self._entry_index:
            provisional_entry = {
                "entry_id": entry_id,
                "entry_nickname": entry_id[:12] if entry_id else "pending",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "user_id": None,
                "safe_text": "",  # Populated later via append_entry
                "centroids": [],
                "ip_hash": "",
                "encrypted_raw_ip": "",
                "encrypted_raw_text": "",
                "crisis_flag": False,
                "hash_from_token_for_deleting_entries": "",
                "is_provisional": True,
            }
            self._entries.append(provisional_entry)
            self._entry_index[entry_id] = provisional_entry

    async def purge_entry_metadata(
        self,
        *,
        entry_id: str = None,  # Kept in keyword args for caller signature compatibility, but bypassed for lookup
        token_hash: str,
    ) -> bool:
        """
        Redacts user personal data from a single targeted submission instance.
        Matches strictly by token_hash across ALL operational modes, as the token hash
        serves as the sole authoritative credential for identifying distinct duplicate rows.
        """
        if not token_hash:
            logger.warning("[EntryRuntime] Purge requested without an authoritative token_hash.")
            return False

        # Complete lookup unification: Both DATABASE and flat-file modes leverage the token hash index map
        target = self._index_for_hashed_tokens_for_deleting_entries.get(token_hash)

        if not target:
            logger.warning(
                "[EntryRuntime] Target entry instance not located for purge with token_hash: %s", 
                token_hash
            )
            return False

        # Extract values directly from the matched structural instance
        stripped_entry_id = target.get("entry_id") or target.get("id")
        
        # Preserve original submission/ingestion time instead of overwriting with the current deletion time
        original_timestamp = target.get("timestamp")

        # Generate an anonymous, unique tombstone value (exactly 39 chars, comfortably under VARCHAR(64))
        # This completely sanitizes the original credential while keeping Postgres PK unique/non-null
        # Generate a highly descriptive, unique tombstone primary key string.
        # Format: "purged-{unix_timestamp}-{16_char_hex}" -> ~32 characters total.
        # This comfortably fits under VARCHAR(64) and gives you exact auditability.
        
        purge_time_epoch = int(time.time())
        purged_tombstone_pk = f"purged-{purge_time_epoch}-{secrets.token_hex(8)}"

        stripped = {
            "entry_id": stripped_entry_id,
            "entry_nickname": None,
            "timestamp": original_timestamp,  # Retains historical record integrity
            "user_id": None,
            "safe_text": "",
            "embedding_file": None,
            "centroids": [],
            "ip_hash": target.get("ip_hash"),
            "encrypted_raw_ip": None,
            "encrypted_raw_text": None,
            "crisis_flag": bool(target.get("crisis_flag", False)),
            "original_hash_for_purge": token_hash,
            "hash_from_token_for_deleting_entries": purged_tombstone_pk, # Original shall be stripped, but postgres requires a unique value to still be there.
            # so we're doing purged-[epochtime]-[randomhex] to stay within postgresql's character limit.
        }

        try:
            # Find the true sequential list index of this specific reference object in the master tracking array
            list_index = self._entries.index(target)
            self._entries[list_index] = stripped
        except ValueError:
            logger.error("[EntryRuntime] Target record detached from main tracking collection array.")
            return False

        # Sync the deletion token tracking index
        self._index_for_hashed_tokens_for_deleting_entries[token_hash] = stripped

        from core.mode_lock import SystemModeLock
        is_database_mode = (SystemModeLock.resolve_operational_mode() == "DATABASE")

        if is_database_mode:
            # Point entry_index to an active record sharing this entry_id if one is still alive
            remaining_active = next(
                (e for e in self._entries 
                 if (e.get("entry_id") == stripped_entry_id or e.get("id") == stripped_entry_id) 
                 and e.get("safe_text") != ""),
                None
            )
            self._entry_index[stripped_entry_id] = remaining_active if remaining_active else stripped
        else:
            self._entry_index[stripped_entry_id] = stripped

        # Clean up vector space projections only if no active duplicate records use this text hash space
        still_has_active = any(
            e for e in self._entries
            if (e.get("entry_id") == stripped_entry_id or e.get("id") == stripped_entry_id)
            and e.get("safe_text") != ""
        )

        if not still_has_active:
            self._window_text.pop(stripped_entry_id, None)
            self._standout_window_flags.pop(stripped_entry_id, None)

        logger.info("[EntryRuntime] Target entry instance successfully redacted in memory via token hash credential.")
        self._dirty_mutation_count += 1
        await self._signal_dirty_queue()
        
        return True

    def get_current_embedding_file(self) -> str:
        return self._npz_path
    
    def _rebuild_entry_index(self) -> None:
        """
        Rebuilds internal structural index maps for O(1) memory lookups.
        In database mode, prioritizes hash_from_token_for_deleting_entries as the authoritative PK.
        """
        from core.mode_lock import SystemModeLock
        operational_mode = SystemModeLock.resolve_operational_mode()

        if operational_mode == "DATABASE":
            # Map every record uniquely by its token hash primary key
            self._index_for_hashed_tokens_for_deleting_entries = {
                e.get("hash_from_token_for_deleting_entries"): e
                for e in self._entries
                if e.get("hash_from_token_for_deleting_entries")
            }
            
            # Sort so active entries take precedence over redacted entries in entry_index lookup
            sorted_entries = sorted(
                self._entries, 
                key=lambda e: 1 if (e.get("safe_text") is not None and e.get("safe_text") != "") else 0
            )
            self._entry_index = {
                (e.get("entry_id") or e.get("id")): e
                for e in sorted_entries
            }
        else:
            # Original flat-file mode isolation logic
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
        await self._signal_dirty_queue()

    def _load_window_embeddings_from_disk(self) -> None:
        self._window_embeddings = {}

        if not os.path.exists(self._window_embeddings_npz_path):
            logger.warning(
                "[NPZ LOAD] missing clause embeddings file: %s",
                self._window_embeddings_npz_path,
            )
            return

        try:
            with np.load(self._window_embeddings_npz_path) as data:
                for k, v in data.items():

                    if not isinstance(v, np.ndarray):
                        continue

                    if v.ndim != 2:
                        continue

                    if v.shape[1] != EMBEDDING_DIM:
                        continue

                    self._window_embeddings[k] = v

        except Exception as e:
            logger.exception(
                "[NPZ LOAD] failed clause embeddings load: %s",
                e,
            )
    
    def _load_window_text_from_disk(self) -> None:
        self._window_text = {}

        if not os.path.exists(self._window_text_npz_path):
            logger.warning(
                "[NPZ LOAD] missing clause windows file: %s",
                self._window_text_npz_path,
            )
            return

        try:
            with np.load(
                self._window_text_npz_path,
                allow_pickle=True
            ) as data:

                for k, v in data.items():

                    if not isinstance(v, np.ndarray):
                        continue

                    self._window_text[k] = v

        except Exception as e:
            logger.exception(
                "[NPZ LOAD] failed clause windows load: %s",
                e,
            )

    def _load_standout_window_flags_from_disk(self) -> None:
        self._standout_window_flags = {}

        if not os.path.exists(self._standout_window_flags_npz_path):
            logger.warning(
                "[NPZ LOAD] missing standout flags file: %s",
                self._standout_window_flags_npz_path,
            )
            return

        try:
            with np.load(self._standout_window_flags_npz_path) as data:

                for k, v in data.items():

                    if not isinstance(v, np.ndarray):
                        continue

                    if v.dtype != np.bool_:
                        continue

                    self._standout_window_flags[k] = v

        except Exception as e:
            logger.exception(
                "[NPZ LOAD] failed standout flags load: %s",
                e,
            )
    
    async def get_window_embeddings(
        self,
        entry_id: str,
    ) -> np.ndarray | None:

        return self._window_embeddings.get(entry_id)

    async def get_window_text(
        self,
        entry_id: str,
    ):

        return self._window_text.get(entry_id)

    async def get_standout_window_flags(
        self,
        entry_id: str,
    ):

        return self._standout_window_flags.get(entry_id)

    async def set_runtime_bundle(
        self,
        entry_id: str,
        *,
        embedding: np.ndarray | None = None,
        window_embeddings: np.ndarray | None = None,
        window_text: np.ndarray | None = None,
        standout_window_flags: np.ndarray | None = None,
    ) -> None:

        if embedding is not None:
            await self.set_embedding(entry_id, embedding)

        if window_embeddings is not None:
            await self.set_window_embeddings(entry_id, window_embeddings)

        if window_text is not None:
            await self.set_window_text(entry_id, window_text)

        if standout_window_flags is not None:
            await self.set_standout_window_flags(entry_id, standout_window_flags)