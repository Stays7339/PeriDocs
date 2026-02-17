# ==========================================
# core/map/mapping_runtime.py
# Save-state: 202602151513 (YYYYMMDDhhmm)
# ==========================================

import logging
from typing import Optional

from core.map.ledger import IdentifierLedger
from core.map.centroids import CentroidSystem

logger = logging.getLogger("peridocs.mapping_runtime")


# ---------------------------------------------------------------------
# Singleton Instances
# ---------------------------------------------------------------------

_ledger: IdentifierLedger = IdentifierLedger()
_centroid_system: CentroidSystem = CentroidSystem(_ledger)

_initialized: bool = False


ledger = _ledger
centroid_system = _centroid_system


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

    # Load ledger into memory
    await ledger.load()

    # Reconstruct centroid state from disk
    await centroid_system.load_state()

    # --- NEW: preload burst/split suggestions ---
    await centroid_system._load_split_suggestions()

    _initialized = True

    if verify:
        await ledger.verify_runtime_state(_centroid_system)

    logger.info("Mapping runtime initialized successfully.")

    


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

