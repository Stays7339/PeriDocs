# ==========================================
# core/mode_lock.py
# Save-state: 2026-07-05T12:59-04:00
# ==========================================

import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

DATA_DIR = Path(os.getenv("PERIDOCS_DATA_DIR", "data"))
MODE_LOCK_PATH = DATA_DIR / ".system_mode_lock"
TMP_LOCK_PATH = DATA_DIR / ".system_mode_lock.tmp"

class SystemModeLock:
    """
    Guarantees the system permanently binds to either DATABASE or OFFLINE storage
    after the initial successful write, preventing mid-lifecycle drift.
    """
    _resolved_mode: str | None = None

    @classmethod
    def is_lock_file_present_on_disk(cls) -> bool:
        """
        Returns True if the sticky system lock file physically exists on disk.
        Used as a veto safety net to prevent split-brain file system drift.
        """
        return MODE_LOCK_PATH.exists()

    @classmethod
    def resolve_operational_mode(cls) -> str:
        """
        Called EXACTLY ONCE during application startup initialization.
        """
        if cls._resolved_mode is not None:
            return cls._resolved_mode

        # 1. Check if a sticky lock file already exists from a previous lifecycle
        if cls.is_lock_file_present_on_disk():
            try:
                locked_mode = MODE_LOCK_PATH.read_text(encoding="utf-8").strip()
                if locked_mode in ("DATABASE", "OFFLINE"):
                    logger.info("[MODE LOCK] Sticky lock active. System anchored to: %s", locked_mode)
                    cls._resolved_mode = locked_mode
                    return cls._resolved_mode
            except Exception as e:
                logger.error("[MODE LOCK] Failed reading lock file: %s. Reverting to environment.", e)

        # 2. Fallback to .env inspection if no lock file exists yet
        env_mode = os.getenv("DATABASE_MODE", "").strip()
        if env_mode in ("PRODUCTION", "SANDBOX"):
            logger.info("[MODE LOCK] No active lock file. .env requests online engine.")
            cls._resolved_mode = "DATABASE"
        else:
            logger.info("[MODE LOCK] No active lock file. Defaulting to  flat-file engine.")
            cls._resolved_mode = "OFFLINE"

        # A3. UTOMATICALLY BURN FUSE HERE INDEPENDENTLY OF THE RUNTIMES
        cls.lock_mode_permanently()

        return cls._resolved_mode

    @classmethod
    def lock_mode_permanently(cls) -> None:
        """
        Burns the fuse. Called immediately after the first successful 
        persistence routine of any module completes.
        """
        if cls.is_lock_file_present_on_disk():
            return # Already locked on disk

        # Check if the initialization sequence was bypassed
        if cls._resolved_mode is None:
            logger.warning("[MODE LOCK] cls._resolved_mode was uninitialized; assuming OFFLINE mode without check.")
            current_mode = "OFFLINE"
        else:
            current_mode = cls._resolved_mode
        
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            
            # Atomic write utilizing your verified .tmp swap protocol
            with open(TMP_LOCK_PATH, "w", encoding="utf-8") as f:
                f.write(current_mode)
                
            os.replace(TMP_LOCK_PATH, MODE_LOCK_PATH)
            logger.warning("[MODE LOCK] FUSE BURNED. System permanently locked to %s mode.", current_mode)
        except Exception as e:
            logger.critical("[MODE LOCK] Catastrophic failure writing sticky mode lock: %s", e)