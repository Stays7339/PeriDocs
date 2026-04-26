# ==========================================
# app/helpers/entry_writing_runtime.py
# Save-state: 2026-04-26T12:09:35-04:00
# ==========================================
import asyncio
import copy
import os
import logging
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

    def __init__(self):
        DATA_DIR = os.getenv("PERIDOCS_DATA_DIR", "data")
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
    # --- APPENDED END ---