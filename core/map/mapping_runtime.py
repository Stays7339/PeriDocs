# ==========================================
# core/map/mapping_runtime.py
# Save-state: 202602041325 (YYYYMMDDhhmm)
# ==========================================

"""
Mapping Runtime Bootstrap for PeriDocs
=======================================

This module defines the *single shared runtime instance* of:

    - IdentifierLedger
    - CentroidSystem

Why this file exists
--------------------

The CentroidSystem is stateful:
    - It holds in-memory centroid objects
    - It maintains an asyncio lock
    - It persists state to disk
    - It must remain consistent across the entire process

If multiple CentroidSystem instances were created,
the application would:
    - Lose deterministic behavior
    - Corrupt event ordering
    - Break replay guarantees
    - Introduce race conditions

Therefore:

    There must be exactly ONE runtime instance.

This file provides that instance.


Design Principles
-----------------

1. No work happens at import time.
   Importing this file does NOT:
       - Load the ledger
       - Load centroid state
       - Touch disk

   That must be done explicitly via `initialize_runtime()`.

2. Deterministic startup.
   Ledger loads first.
   Centroid state loads second.

3. Safe for:
       - FastAPI
       - CLI tools
       - Background workers
       - Unit tests

4. No circular imports.
   This module only imports:
       - IdentifierLedger
       - CentroidSystem

   Nothing inside ledger.py or centroids.py imports this file.


How to Use in FastAPI
---------------------

In your app startup:

    from core.map.mapping_runtime import initialize_runtime

    @app.on_event("startup")
    async def startup():
        await initialize_runtime()

Then anywhere in the codebase:

    from core.map.mapping_runtime import centroid_system

This guarantees a single shared system.


Lifecycle Overview
------------------

1. Ledger is loaded into memory.
2. CentroidSystem loads persisted centroid JSON files.
3. System is ready for:
       - create_precentroid
       - approve_precentroid
       - add_saaje
       - remove_saaje
       - drift analysis
       - burst logic


Threading / Concurrency Model
-----------------------------

CentroidSystem owns:
    - an asyncio.Lock
    - in-memory state

All mutation must occur through CentroidSystem methods.
Never mutate internal state directly.

This module does NOT expose any raw mutable state.


Production Guarantees
---------------------

- Single authoritative ledger instance
- Single authoritative centroid system
- Deterministic replay capability
- Explicit initialization
- No hidden side effects
"""

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

