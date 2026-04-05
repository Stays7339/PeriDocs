# ==========================================
# core/map/mapping_runtime.py
# Save-state: 2026-04-05T13:20:40-04:00 (YYYYMMDDhhmm)
# ==========================================
import os
import logging
import asyncio
import zipfile
from typing import Optional
from pathlib import Path
from datetime import datetime

from core.map.ledger import IdentifierLedger
from core.map.centroids import CentroidSystem
from app.helpers.entry_writing_runtime import EntryWritingRuntime

logger = logging.getLogger("peridocs.core.map.mapping_runtime")

DATA_DIR = os.getenv("PERIDOCS_DATA_DIR", "data")
ENTRIES_DIR = os.path.join(DATA_DIR, "entries")
STATE_DIR = os.path.join(DATA_DIR, "centroids")
SUGGESTIONS_DIR = os.path.join(DATA_DIR, "suggestions")
ARCHIVE_DIR = os.path.join(DATA_DIR, "archive")

# ---------------------------------------------------------------------
# Singleton Instances
# ---------------------------------------------------------------------

_ledger: IdentifierLedger = IdentifierLedger()
_centroid_system: CentroidSystem = CentroidSystem(_ledger)
_entry_runtime: EntryWritingRuntime = EntryWritingRuntime()

_initialized: bool = False


ledger = _ledger
centroid_system = _centroid_system
entry_runtime = _entry_runtime


# ---------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------

async def initialize_runtime(force_reload: bool = False, verify: bool = False) -> None:
    """
    Initialize the mapping runtime.

    This MUST be called exactly once during application startup.

    What this does:
        1. Loads ledger from disk into memory.
        2. Reconstructs centroid state from persisted JSON.
        3. Ensures deterministic replay order enforcement.

    Parameters
    ----------
    force_reload : bool
        If True:
            - Forces ledger reload
            - Forces centroid state reload
        If False:
            - Skips if already initialized

    Safe to call multiple times.
    """

    global _initialized

    if _initialized and not force_reload:
        logger.info("Mapping runtime already initialized.")
        return

    logger.info("Initializing mapping runtime...")
    logger.info("Centroids loaded: %s", list(centroid_system._centroids.keys()))

    # Load ledger into memory
    await ledger.load()

    # Reconstruct centroid state from disk
    await centroid_system.load_state()

    # --- VERIFY centroids against ledger ---
    try:
        await ledger.verify_runtime_state(centroid_system)
        # Startup-level integrity check (JSON/NPZ)
        await centroid_system._verify_integrity_on_startup()
    except Exception as e:
        logger.error("[initialize_runtime] Centroid/Ledger mismatch or file integrity failure: %s", e)
        # Flush user entries safely here if needed (optional)
        # For a non-literal skeletal example: await entry.flush_pending_entries()
        raise RuntimeError("Mapping runtime startup aborted due to integrity failure")

    # Preload burst/split suggestions
    await centroid_system._load_split_suggestions()

    await entry_runtime.initialize()

    _initialized = True

    if verify:
        await ledger.verify_runtime_state(_centroid_system)
    logger.info("Centroids loaded: %s", list(centroid_system._centroids.keys()))
    logger.info("Mapping runtime initialized successfully.")

    # Schedule periodic check after initialization
    asyncio.create_task(periodic_integrity_check())
    
# Define one central interval
PERIODIC_INTEGRITY_INTERVAL_IN_SECONDS = 300  # 5 minutes, change this once

async def periodic_integrity_check():
    """
    Periodically verify centroid integrity and create a zip backup if checks pass.
    """
    backup_dir = Path.cwd()  # project root
    backups_folder = backup_dir / "backups-for-the-main-data-folder"
    backups_folder.mkdir(exist_ok=True)

    while True:
        try:
            # Verify integrity
            await _centroid_system._verify_integrity_on_startup()

            # Create zip backup of full data folder
            timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H-%M-%SZ")
            backup_name = backups_folder / f"peridocs_data_folder_backup_{timestamp}.zip"

            # Recursively zip DATA_DIR
            data_dir_path = Path(DATA_DIR)
            with zipfile.ZipFile(backup_name, "w", zipfile.ZIP_DEFLATED) as zf:
                for file_path in data_dir_path.rglob("*"):
                    zf.write(file_path, file_path.relative_to(data_dir_path))

            logger.info(f"[periodic_integrity_check] Backup created: {backup_name}")

        except Exception as e:
            logger.error(f"[periodic_integrity_check] Integrity check or backup failed: {e}")

        await asyncio.sleep(PERIODIC_INTEGRITY_INTERVAL_IN_SECONDS)

# ---------------------------------------------------------------------
# Health / Debug Utilities
# ---------------------------------------------------------------------

def is_initialized() -> bool:
    """
    Return whether the mapping runtime has been initialized.
    """
    return _initialized


async def reload_runtime() -> None:
    """
    Force full reload of ledger and centroid state.

    Intended for:
        - administrative maintenance
        - deterministic replay verification
        - test harness resets

    Equivalent to:
        initialize_runtime(force_reload=True)
    """
    await initialize_runtime(force_reload=True)
    await ledger.verify_runtime_state(_centroid_system)

