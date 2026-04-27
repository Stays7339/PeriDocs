# ==========================================
# app/helpers/entry_writing_runtime.py
# Save-state: 2026-04-27T02:06:08-04:00
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
from app.helpers.json_safe import json_safe

logger = logging.getLogger(__name__)



def get_npz_window_path(base_name: str) -> str:
    now = datetime.now(timezone.utc)
    window = now.hour // 6
    timestamp = now.strftime("%Y%m%d") + f"_{window}"

    return f"data/entries/{base_name}_dump_{timestamp}.npz"

EMBEDDING_DIM = 1024
entries_mean_embed_file = get_npz_window_path("entries_mean_embeddings")

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
        self._npz_path = get_npz_window_path("entries_mean_embeddings")     
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        """
        Load entries.json into memory once.

        Safe to call multiple times; only loads on first call.
        """
        logger.info("[EntryWritingRuntime] Starting initialize()")
        async with self._lock:
            if self._initialized:
                return

            self._entries = self._load_entries_from_disk()
            self._initialized = True
        logger.info("[EntryWritingRuntime] Finished initialize()")

    async def _verify_integrity_on_startup(self) -> None:
        """
        Startup-time integrity validation for entry system.

        This enforces strict consistency between:
            1. ledger.json (authoritative event log)
            2. entries.json (canonical entry registry)
            3. embedding dumps:
                - entry_clause_embeddings_dump[YYYYMMDD]_[0-3].npz
                - entry_mean_embeddings_dump[YYYYMMDD]_[0-3].npz
                - entry_standout_flags_dump[YYYYMMDD]_[0-3].npz

        HARD GOAL:
            - If an entry_id appears anywhere in ledger.json,
            it MUST exist in entries.json AND all embedding stores.
            - Deleted entries STILL retain embeddings (no exceptions).
            - Missing entries or embeddings cause immediate RuntimeError.

        For integrity of Entries:

        ALWAYS load from _load_entries_from_disk
        NEVER rely on _entries, because Even though _entries is initialized in initialize(), 
        your integrity check runs in a startup phase where:
        _entries may still be empty
        _entries may be stale if reload hasn’t happened
        _entries may not reflect disk reality if crash occurred mid-write

        integrity checks should be lock-free or minimally locked
        Startup checks are meant to detect corruption, not assume safe concurrency state.
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

        clause_pattern = "entries_clause_embeddings_dump_*.npz"
        mean_pattern = "entries_mean_embeddings_dump_*_*.npz"
        standout_pattern = "entries_standout_flags_dump_*_*.npz"

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
        # LOAD ALL EMBEDDING FILES
        # ------------------------------------------------------------
        clause_files = glob.glob(os.path.join(entries_dir, clause_pattern))
        mean_files = glob.glob(os.path.join(entries_dir, mean_pattern))
        standout_files = glob.glob(os.path.join(entries_dir, standout_pattern))

        # --- strict file existence + emptiness validation ---
        if not mean_files:
            raise RuntimeError("[entry_runtime] No mean embedding dump files found")

        # ensure files are not empty / unreadable at OS level
        for f in mean_files:
            try:
                if os.path.getsize(f) == 0:
                    raise RuntimeError(f"Empty embedding file detected: {f}")
            except OSError as e:
                raise RuntimeError(f"Unreadable embedding file: {f} | {e}")
        
        # ------------------------------------------------------------
        # CHECK 2: EMBEDDING VALIDATION
        # ------------------------------------------------------------
        invalid_embeddings = []
        missing_embeddings = []

        def validate_npz(files, label):
            for file_path in files:
                try:
                    data = np.load(file_path)
                except Exception as e:
                    logger.error("[entry_runtime] Failed to load %s: %s", file_path, e)
                    raise RuntimeError(f"Corrupt embedding file: {file_path}")

                for key, vec in data.items():
                    if not isinstance(key, str):
                        raise RuntimeError(f"Invalid embedding key type in {file_path}")
                    
                    entry_id = key  # assuming key == entry_id

                    # ---  strict key existence check ---
                    if entry_id not in ledger_entry_ids:
                        continue  


                    # --- strict vector validation ---
                    if vec is None:
                        invalid_embeddings.append((entry_id, label, "missing vector (None)"))
                        continue

                    if not isinstance(vec, np.ndarray):
                        invalid_embeddings.append((entry_id, label, "not ndarray"))
                        continue

                    if vec.size == 0:
                        invalid_embeddings.append((entry_id, label, "empty vector"))

                    if np.all(vec == 0):
                        invalid_embeddings.append((entry_id, label, "zero vector"))
                        continue
                    

        validate_npz(clause_files, "clause")
        validate_npz(mean_files, "mean")
        validate_npz(standout_files, "standout")

        # ------------------------------------------------------------
        # FINAL FAILURE CONDITIONS
        # ------------------------------------------------------------
        if invalid_embeddings:
            for eid, label, reason in invalid_embeddings:
                logger.error(
                    "[entry_runtime] Invalid embedding: %s | %s | %s",
                    eid, label, reason
                )
            raise RuntimeError("Entry embedding integrity failure (invalid vectors detected)")

        if missing_embeddings:
            for eid, label in missing_embeddings:
                logger.error(
                    "[entry_runtime] Missing embedding: %s | %s",
                    eid, label
                )
            raise RuntimeError("Entry embedding integrity failure (missing vectors detected)")

        # ------------------------------------------------------------
        # IF SUCCESSFUL
        # ------------------------------------------------------------
        logger.info("[entry_runtime] All entries passed integrity check.")


    async def append_entry(self, entry: Dict[str, Any]) -> None:
        """
        Append a new entry and persist.

        Memory is authoritative. Disk is write-only durability.
        No runtime reconciliation against disk is performed.
        """

        async with self._lock:

            # ----------------------------
            # Strict safety validation
            # ----------------------------
            if not isinstance(entry, dict):
                raise RuntimeError("Invalid entry type: must be dict")

            if entry.get("crisis_flag") is True:
                return

            if entry.get("safe_text") is None:
                return

            if "entry_id" not in entry and "id" not in entry:
                raise RuntimeError("Entry missing identifier field")

            entry_id = entry.get("entry_id") or entry.get("id")

            # ----------------------------
            # In-memory uniqueness awareness (non-enforcing)
            # ----------------------------
            existing_ids = {e.get("entry_id") or e.get("id") for e in self._entries}

            if entry_id in existing_ids:
                logger.warning(
                    "[EntryRuntime] duplicate entry_id detected (appending anyway): %s",
                    entry_id
                )

            # ----------------------------
            # Append to runtime memory (source of truth)
            # ----------------------------
            self._entries.append(entry)

            # ----------------------------
            # Persist snapshot (one-way write)
            # ----------------------------
            await self.persist()

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
        - persist() must never validate again
        """

        async with self._lock:

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
            # STORE CANONICALIZED RESULT
            # ------------------------------------------
            self._embeddings[entry_id] = embedding
    
    async def persist(self) -> None:
        """
        Deterministic snapshot persistence.

        Guarantees:
        - JSON is atomically written
        - NPZ is atomically written
        - no partial state is ever visible
        - no validation or coercion occurs here
        """

        async with self._lock:

            # ------------------------------------------
            # JSON SNAPSHOT (source of truth)
            # ------------------------------------------
            snapshot = json_safe(self._entries)

            json_tmp = self._entries_path + ".tmp"

            with open(json_tmp, "w", encoding="utf-8") as f:
                json.dump(snapshot, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())

            os.replace(json_tmp, self._entries_path)

            # ------------------------------------------
            # NPZ SNAPSHOT (derived embeddings cache)
            # ------------------------------------------
            npz_path = entries_mean_embed_file
            npz_tmp = npz_path + ".tmp"

            # IMPORTANT:
            # assumes embeddings are already validated at set_embedding()
            embedding_snapshot = self._embeddings

            np.savez_compressed(npz_tmp, **embedding_snapshot)
            os.sync()  # coarse-grained but safe fallback
            os.replace(npz_tmp, npz_path)

            logger.info(
                "[PersistOK] entries=%d embeddings=%d",
                len(self._entries),
                len(self._embeddings),
            )

    def _load_entries_from_disk(self) -> List[Dict[str, Any]]:
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

    async def get_embedding(self, entry_id: str):
        """
        Safe in-memory embedding read.

        Uses same lock to avoid race conditions with writes.
        """
        async with self._lock:
            return self._embeddings.get(entry_id)

    async def get_all_embeddings(self):
        async with self._lock:
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

        async with self._lock:

            # ----------------------------
            # FIND TARGET IN MEMORY
            # ----------------------------
            target = None
            for entry in self._entries:
                if entry.get("hash_from_token_for_deleting_entries") == token_hash:
                    target = entry
                    break

            if not target:
                logger.warning(
                    "[EntryRuntime] Entry not found during strip_entry."
                )
                return False

            # ----------------------------
            # STRIP
            # ----------------------------
            stripped = {
                "entry_id": target.get("entry_id") or target.get("id"),
                "embedding_file": target.get("embedding_file"),
                "crisis_flag": target.get("crisis_flag"),
            }

            index = self._entries.index(target)
            self._entries[index] = stripped

            # ----------------------------
            # PERSIST
            # ----------------------------
            await self.persist()

            logger.info(f"[EntryRuntime] Entry {entry_id} stripped and persisted.")

            return True
    def get_current_embedding_file(self) -> str:
        return self._npz_path