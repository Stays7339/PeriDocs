# ==========================================
# core/reasoning/heuristic_loader.py
# Save-state: 2026-07-12T16:18-04:00
# ==========================================
import json
import os
import logging
from pathlib import Path
from typing import List, Dict, Any
from core.mode_lock import SystemModeLock

logger = logging.getLogger(__name__)
HEURISTICS_FILE = os.path.join("data", "reasoning", "heuristics.json")

class ReasoningRegistryRuntime:
    def __init__(self):
        self._heuristics: List[Dict[str, Any]] = []
        self._concepts: List[Dict[str, str]] = []
        self._initialized = False

    async def initialize(self, db_engine):
        if self._initialized:
            return

        if SystemModeLock.resolve_operational_mode() == "DATABASE":
            try:
                # Use the connection pattern (fixes your previous AttributeError)
                async with db_engine.pool.connection() as conn:
                    async with conn.cursor() as cur:
                        # 1. Load Heuristics
                        await cur.execute("SELECT heuristic_id, givens, outputs FROM kb_schema.heuristics;")
                        h_rows = await cur.fetchall()
                        self._heuristics = [
                            {"heuristic_id": r[0], "givens": r[1], "outputs": r[2]}
                            for r in h_rows
                        ]

                        # 2. Load Concepts
                        await cur.execute("SELECT concept_id, label, description FROM kb_schema.concepts;")
                        c_rows = await cur.fetchall()
                        self._concepts = [
                            {"id": r[0], "label": r[1], "description": r[2]}
                            for r in c_rows
                        ]
                
                self._initialized = True
                logger.info("[ReasoningRegistryRuntime] Initialized from DB.")
                return
            except Exception as db_err:
                logger.error("[ReasoningRegistryRuntime] DB Load failed: %s", db_err)
                if SystemModeLock.is_lock_file_present_on_disk():
                    raise db_err

        # --- FLAT FILE FALLBACK ---
        if os.path.exists(HEURISTICS_FILE):
            with open(HEURISTICS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                self._heuristics = [h for h in data if "heuristic_id" in h]
        
        self._initialized = True

# --- GLOBAL SINGLETON ---
registry = ReasoningRegistryRuntime()