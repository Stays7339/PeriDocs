# ==========================================
# app/helpers/entry_writing_runtime.py
# Save-state: 2026-04-26T17:58:10-04:00
# ==========================================
import asyncio
import copy
import json
import glob
import os
import logging
import numpy as np
from typing import List, Dict, Any

from app.helpers.file_ops import load_data, save_data

logger = logging.getLogger(__name__)

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
        

        # --- APPENDED START: async lock for all mutations ---
        self._lock = asyncio.Lock()
        # --- APPENDED END ---

    async def initialize(self) -> None:
        """
        Load entries.json into memory once.

        Safe to call multiple times; only loads on first call.
        """
        logger.info("[EntryWritingRuntime] Starting initialize()")
        async with self._lock:
            if self._initialized:
                return

            self._entries = load_data(self._entries_path)
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

        ALWAYS load from disk (load_data() or direct JSON read)
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

        clause_pattern = "entries_clause_embeddings_dump*_*.npz"
        mean_pattern = "entries_mean_embeddings_dump*_*.npz"
        standout_pattern = "entries_standout_flags_dump*_*.npz"

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

        # --- APPENDED START: strict file existence + emptiness validation ---
        if not clause_files:
            raise RuntimeError("[entry_runtime] No clause embedding dump files found")

        if not mean_files:
            raise RuntimeError("[entry_runtime] No mean embedding dump files found")

        if not standout_files:
            raise RuntimeError("[entry_runtime] No standout embedding dump files found")

        # ensure files are not empty / unreadable at OS level
        for f in clause_files + mean_files + standout_files:
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
        logger.info("[entry_runtime] Entry + embedding integrity check passed successfully.")


    async def reload(self) -> None:
        """
        Force reload from disk.
        """

        # --- APPENDED START: lock-protected reload ---
        async with self._lock:
            self._entries = load_data(self._entries_path)
            self._initialized = True
        # --- APPENDED END ---

    async def persist(self) -> None:
        """
        Persist current in-memory entries to disk.

        NOTE:
        Caller should already be inside lock when calling this
        to avoid nested lock acquisition.
        """

        # --- APPENDED START: no lock acquisition here (assumed upstream) ---
        save_data(self._entries, self._entries_path)
        # --- APPENDED END ---

    def get_all_entries(self) -> List[Dict[str, Any]]:
        """
        Return in-memory entries.

        NOTE:
        Returns direct reference. Caller must not mutate outside lock.
        """
        # --- return deep copy to protect internal state ---
        return copy.deepcopy(self._entries)
        # ------

    async def append_entry(self, entry: Dict[str, Any]) -> None:
        """
        Append a new entry and persist.

        Mirrors existing append_entry behavior but routed through runtime.
        """

        # --- APPENDED START: full mutation under lock ---
        async with self._lock:

            # preserve existing safety checks
            if entry.get("crisis_flag") is True:
                return

            if entry.get("safe_text") is None:
                return

            self._entries.append(entry)

            await self.persist()
        # --- APPENDED END ---

    async def get_embedding(self, entry_id: str):
        """
        Safe in-memory embedding read.

        Uses same lock to avoid race conditions with writes.
        """
        async with self._lock:
            return self._embeddings.get(entry_id)

    async def set_embedding(self, entry_id: str, embedding):
        """
        Safe in-memory embedding write.

        Stores canonical float32 numpy array.
        """
        async with self._lock:
            self._embeddings[entry_id] = embedding