# ==========================================
# core/map/mapping_runtime.py
# Save-state: 2026-04-28T21:59:05-04:00 (YYYYMMDDhhmm)
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

logger = logging.getLogger(__name__)

DATA_DIR = os.getenv("PERIDOCS_DATA_DIR", "data")
ENTRIES_DIR = os.path.join(DATA_DIR, "entries")
STATE_DIR = os.path.join(DATA_DIR, "centroids")
SUGGESTIONS_DIR = os.path.join(DATA_DIR, "suggestions")
ARCHIVE_DIR = os.path.join(DATA_DIR, "archive")

# ---------------------------------------------------------------------
# Singleton Instances
# ---------------------------------------------------------------------

_ledger = IdentifierLedger()
_entry_runtime = EntryWritingRuntime(_ledger)
_centroid_system = CentroidSystem(_ledger, _entry_runtime)


# (_ledger) is used so that if integrity fails, you can trace causality directly:
# “ledger state caused entry validation failure” 
# rather than: “some global singleton state was inconsistent somewhere”


_initialized: bool = False
_runtime_ready: bool = False  
_boot_in_progress: bool = False


ledger = _ledger
centroid_system = _centroid_system
entry_runtime = _entry_runtime
"""
# We're redefining here so that we can add in additional functions 
# if we'd in the future, without needing to find and replace the variable.
"""

# ---------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------

def is_runtime_ready() -> bool:
    return _runtime_ready

def is_runtime_starting() -> bool:
    return _boot_in_progress

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

    global _initialized, _runtime_ready, _boot_in_progress

    if _initialized and not force_reload:
        return

    _boot_in_progress = True

    # Load ledger into memory
    await ledger.load()

    # entries should always load before centroids, since centroids are derived from entries
    await entry_runtime.initialize()
    await entry_runtime._verify_integrity_on_startup()
    logger.info("ENTRY_RUNTIME TYPE: %s", type(entry_runtime))
    logger.info("ENTRY_RUNTIME INIT FUNC: %s", getattr(entry_runtime, 'initialize', None))

    await centroid_system.load_state()

    await ledger.verify_runtime_state(centroid_system)

    await centroid_system._verify_integrity_on_startup()

    # second pass just to confirm
    await entry_runtime.initialize()
    await entry_runtime._verify_integrity_on_startup()

    _initialized = True
    _runtime_ready = True
    _boot_in_progress = False
    logger.info("Mapping runtime is now READY.")

    # Schedule periodic check after initialization
    asyncio.create_task(periodic_integrity_check())


# Recheck that all the files are in order every once in a while
# In seconds
PERIODIC_INTEGRITY_INTERVAL_IN_SECONDS = 150


async def periodic_integrity_check():
    """
    Periodically verify centroid integrity and create a zip backup if checks pass.
    """
    project_root = Path.cwd()  # project root
    backups_folder = project_root / "backups-for-the-main-data-folder"
    backups_folder.mkdir(exist_ok=True)

    while True:
        try:
            # Verify integrity
            await _centroid_system._verify_integrity_on_startup()
            await _entry_runtime._verify_integrity_on_startup()

            # Create name for the zip file backup of full data folder
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

