# ==========================================
# app/credentialing/account_runtime.py
# save-state 2026-05-16T10:32:35-04:00
# ==========================================

import os
import json
import copy
import time
import secrets
import asyncio
import logging

from typing import Dict, Optional, Any
from pathlib import Path

from app.credentialing.security_fundamentals import (
    encrypt_value,
    decrypt_value,
    hash_password,
    verify_password,
    verify_password,
    generate_totp_code_secret,
    verify_totp_code,
)

logger = logging.getLogger(__name__)


# =========================================================
# CONFIGURATION
# =========================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATA_DIRECTORY = Path(
    os.getenv("PERIDOCS_DATA_DIR", PROJECT_ROOT / "data")
)

ACCOUNT_DIRECTORY = DATA_DIRECTORY / "accounts"

ENCRYPTED_ACCOUNT_FILE = ACCOUNT_DIRECTORY / "accounts.encrypted.json"
TEMPORARY_WRITE_FILE = ENCRYPTED_ACCOUNT_FILE.with_suffix(".tmp")

# =========================================================
# ACCOUNT RUNTIME
# =========================================================

class AccountRuntime:
    """
    Singleton-style runtime for PeriDocs accounts.

    Responsibilities
    ----------------
    - Hold encrypted account state in memory
    - Serialize all account mutations
    - Persist encrypted snapshots atomically
    - Validate integrity at startup
    - Prevent unsafe concurrent writes

    Explicit Non-Responsibilities
    -----------------------------
    - Does not manage sessions
    - Does not manage CSRF
    - Does not manage routing
    - Does not generate TOTP secrets
    - Does not verify TOTP codes

    Architectural Rule
    ------------------
    Routes should NEVER directly mutate account files.

    All account changes MUST flow through:
        account_runtime
    """

    def __init__(self):

        # -----------------------------------------
        # authoritative in-memory account state
        # -----------------------------------------

        self._accounts_by_username: Dict[str, Dict[str, Any]] = {}

        # -----------------------------------------
        # startup state
        # -----------------------------------------

        self._initialized = False

        # -----------------------------------------
        # prevents simultaneous mutation corruption
        # -----------------------------------------

        self._account_write_lock = asyncio.Lock()

        # -----------------------------------------
        # queued mutation processing
        # even if traffic is low, this guarantees:
        #
        # - deterministic write order
        # - future scalability
        # - centralized mutation boundary
        # -----------------------------------------

        self._account_operation_queue = asyncio.Queue()

        # -----------------------------------------
        # background queue worker task
        # -----------------------------------------

        self._background_queue_worker = None

        self._pending_account_setups = {}

        self._pending_setup_expiration_seconds = 600

        self._dibs_on_first_admin_account = False

        # =====================================================
        # FLUSH CONTROL (ADAPTIVE, TRAFFIC-AWARE)
        # =====================================================

        self._recent_queue_processing_timestamps: list[float] = []

        self._last_account_disk_flush_time: float = 0.0

        self._pending_mutations_since_last_flush: int = 0

        self._minimum_flush_interval_seconds: float = 2.0
        self._maximum_flush_interval_seconds: float = 30.0

        self._flush_pressure_smoothing_window_seconds: float = 10.0
    
    async def shutdown(self):
    
        await self._account_operation_queue.join()
        await self._persist_accounts_to_disk()
    

    # =====================================================
    # INITIALIZATION
    # =====================================================

    async def initialize(self):
        """
        Initialize runtime exactly once.

        Responsibilities:
        - create account directory if missing
        - load encrypted account file
        - validate integrity
        - rebuild indexes
        - start queue worker
        """

        async with self._account_write_lock:

            if self._initialized:
                return

            logger.info(
                "[AccountRuntime] Starting initialization."
            )

            ACCOUNT_DIRECTORY.mkdir(parents=True, exist_ok=True)

            await self._load_accounts_from_disk()

            await self._verify_integrity_of_loaded_accounts()

            self._background_queue_worker = (
                asyncio.create_task(
                    self._account_operation_worker()
                )
            )

            self._initialized = True

            logger.info(
                "[AccountRuntime] Initialization complete."
            )

    # =====================================================
    # QUEUE WORKER
    # =====================================================

    async def _account_operation_worker(self):
        """
        Processes queued mutations and performs adaptive flushes
        based on observed system load.
        """

        logger.info("[AccountRuntime] Queue worker started.")

        while True:

            operation = await self._account_operation_queue.get()

            try:
                await operation()

                self._pending_mutations_since_last_flush += 1
                self._record_queue_processing_timestamp()

                if self._should_flush_account_state_to_disk():
                    await self._flush_account_state_if_needed()

            except Exception as error:
                logger.exception(
                    "[AccountRuntime] Queue operation failed: %s",
                    error
                )

            finally:
                self._account_operation_queue.task_done()

    def _record_queue_processing_timestamp(self):
        now = time.time()

        self._recent_queue_processing_timestamps.append(now)

        cutoff = now - self._flush_pressure_smoothing_window_seconds

        self._recent_queue_processing_timestamps = [
            t for t in self._recent_queue_processing_timestamps
            if t >= cutoff
        ]

    def _estimate_current_write_pressure(self) -> float:
        now = time.time()

        window = self._flush_pressure_smoothing_window_seconds

        ops = len(self._recent_queue_processing_timestamps)

        ops_per_second = ops / max(window, 1e-6)

        queue_depth = self._account_operation_queue.qsize()

        queue_pressure = min(queue_depth / 50.0, 1.0)
        rate_pressure = min(ops_per_second / 5.0, 1.0)

        return max(queue_pressure, rate_pressure)

    def _should_flush_account_state_to_disk(self) -> bool:
        """
        Determines whether disk flush should occur based on:
        - recent load
        - time since last flush
        - accumulated mutation count
        """

        now = time.time()

        pressure = self._estimate_current_write_pressure()

        # dynamically stretch flush interval under load
        adaptive_interval = self._minimum_flush_interval_seconds + (
            (1.0 - pressure) * (self._maximum_flush_interval_seconds - self._minimum_flush_interval_seconds)
        )

        time_since_flush = now - self._last_account_disk_flush_time

        if self._pending_mutations_since_last_flush == 0:
            return False

        if time_since_flush < adaptive_min_interval:
            return False

        # high pressure → delay flush more aggressively
        if pressure > 0.7 and time_since_flush < self._maximum_flush_interval_seconds:
            return False

        return True

    async def _flush_account_state_if_needed(self):
        """
        Writes in-memory account state to disk.
        """

        await self._persist_accounts_to_disk()

        self._last_account_disk_flush_time = time.time()
        self._pending_mutations_since_last_flush = 0

    async def enqueue_account_operation(
        self,
        operation
    ):
        """
        Queue a mutation operation.

        Example:
            await runtime.enqueue_account_operation(
                some_async_function
            )
        """

        await self._account_operation_queue.put(
            operation
        )

    # =====================================================
    # ACCOUNT CREATION
    # =====================================================

    
    async def call_dibs_on_first_admin_account(self) -> bool:
        async with self._account_write_lock:
            if self._dibs_on_first_admin_account:
                return False
            self._dibs_on_first_admin_account = True
            return True

    
    async def begin_account_setup(
        self,
        *,
        username: str,
        plaintext_password: str,
    ):
        """
        Begins staged account setup.

        Account is NOT persisted yet.

        Flow:
        - generate TOTP secret
        - hold staged state in memory
        - require valid TOTP before persistence
        """

        if await self.system_has_accounts():
            # optional: later replace with invite system
            pass

        async with self._account_write_lock:

            self._cleanup_expired_pending_setups()

            if username in self._accounts_by_username:

                raise RuntimeError(
                    "Username already exists."
                )

            for pending in self._pending_account_setups.values():

                if pending["username"] == username:

                    raise RuntimeError(
                        "Username already pending setup."
                    )

            setup_token = secrets.token_urlsafe(32)

            generated_totp_secret = (
                generate_totp_code_secret()
            )

            self._pending_account_setups[
                setup_token
            ] = {

                "username":
                    username,

                "plaintext_password":
                    plaintext_password,

                "generated_totp_secret":
                    generated_totp_secret,

                "created_at":
                    time.time(),

                "expires_at":
                    (
                        time.time()
                        + self._pending_setup_expiration_seconds
                    ),
            }

            return {
                "setup_token":
                    setup_token,

                "totp_secret":
                    generated_totp_secret,
            }
    
    async def complete_account_setup(
        self,
        *,
        setup_token: str,
        totp_code: str,
    ):
        """
        Finalizes account setup ONLY after valid TOTP.
        """

        async with self._account_write_lock:

            is_first = len(self._accounts_by_username) == 0
            role = "administrator" if is_first else "ordinary"


            self._cleanup_expired_pending_setups()

            pending = self._pending_account_setups.get(
                setup_token
            )

            if not pending:

                raise RuntimeError(
                    "Invalid setup token."
                )

            if time.time() > pending["expires_at"]:

                self._pending_account_setups.pop(
                    setup_token,
                    None
                )

                raise RuntimeError(
                    "Setup token expired."
                )

            generated_totp_secret = (
                pending["generated_totp_secret"]
            )

            if not verify_totp_code(
                generated_totp_secret,
                totp_code
            ):

                raise RuntimeError(
                    "Invalid TOTP code."
                )

            username = pending["username"]

            plaintext_password = (
                pending["plaintext_password"]
            )

            self._accounts_by_username[
                username
            ] = {

                "user_id":
                    secrets.token_hex(32),

                "username":
                    username,

                "password_hash":
                    hash_password(
                        plaintext_password
                    ),

                "time_secret_encrypted":
                    encrypt_value(
                        generated_totp_secret
                    ),

                "role":
                    role,

                "created_at":
                    time.time(),
            }

            self._pending_account_setups.pop(
                setup_token,
                None
            )

            await self._persist_accounts_to_disk()

            logger.info(
                "[AccountRuntime] Account setup completed: %s",
                username
            )
    # =====================================================
    # AUTHENTICATION
    # =====================================================

    async def authenticate_username_and_password(
        self,
        *,
        username: str,
        plaintext_password: str,
    ) -> bool:
        """
        Verify username + password combination.
        """

        async with self._account_write_lock:

            user = self._accounts_by_username.get(
                username
            )

            if not user:
                return False

            return verify_password(
                user["password_hash"],
                plaintext_password
            )

    async def get_decrypted_totp_secret(
        self,
        username: str
    ) -> Optional[str]:
        """
        Return decrypted TOTP secret for runtime use.

        IMPORTANT:
        - secret remains encrypted at rest
        - decryption only occurs during runtime
        """

        async with self._account_write_lock:

            user = self._accounts_by_username.get(
                username
            )

            if not user:
                return None

            encrypted_secret = user.get(
                "time_secret_encrypted"
            )

            if not encrypted_secret:
                return None

            return decrypt_value(
                encrypted_secret
            )

    # =====================================================
    # LOOKUPS
    # =====================================================

    async def has_administrator_accounts(self) -> bool:
        """
        Returns True if ANY administrator exists.
        """

        async with self._account_write_lock:

            for user in self._accounts_by_username.values():

                if user.get("role") == "administrator":
                    return True

            return False

    async def system_has_accounts(self) -> bool:

        async with self._account_write_lock:

            return bool(self._accounts_by_username)

    async def get_user_role(
        self,
        username: str
    ) -> Optional[str]:

        async with self._account_write_lock:

            user = self._accounts_by_username.get(
                username
            )

            if not user:
                return None

            return user.get("role")

    async def get_user_snapshot(
        self,
        username: str
    ) -> Optional[Dict[str, Any]]:
        """
        Returns deep copy of user state.

        Internal state MUST NEVER be exposed directly.
        """

        async with self._account_write_lock:

            user = self._accounts_by_username.get(
                username
            )

            if not user:
                return None

            return copy.deepcopy(user)

    async def get_all_accounts_snapshot(self):
        """
        Safe full snapshot export.
        """

        async with self._account_write_lock:

            return copy.deepcopy(
                self._accounts_by_username
            )

    # =====================================================
    # PERSISTENCE
    # =====================================================
    async def _persist_accounts_to_disk(self):
        """
        Atomic encrypted persistence.

        Guarantees:
        - no partial writes
        - no visible corruption window
        - encrypted persistence only
        """

        ACCOUNT_DIRECTORY.mkdir(parents=True, exist_ok=True)

        serialized_account_data = json.dumps(
            self._accounts_by_username,
            ensure_ascii=False,
            indent=2
        )

        encrypted_payload = encrypt_value(serialized_account_data)

        # ensure temp file path is safe (Pathlib usage)
        temp_path = TEMPORARY_WRITE_FILE

        with open(temp_path, "w", encoding="utf-8") as temporary_file:
            temporary_file.write(encrypted_payload)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())

        # atomic replace (Pathlib preferred)
        temp_path.replace(ENCRYPTED_ACCOUNT_FILE)

        # chmod ONLY after file exists
        try:
            ENCRYPTED_ACCOUNT_FILE.chmod(0o600)
        except PermissionError:
            logger.warning(
                "[AccountRuntime] Failed to harden file permissions for encrypted account."
            )

        logger.info(
            "[AccountRuntime] Persisted encrypted account snapshot."
        )
        
    async def _load_accounts_from_disk(self):
        """
        Load encrypted accounts into memory.
        """

        if not os.path.exists(
            ENCRYPTED_ACCOUNT_FILE
        ):

            logger.warning(
                "[AccountRuntime] No account file found. Starting clean."
            )

            self._accounts_by_username = {}

            return

        try:

            with open(
                ENCRYPTED_ACCOUNT_FILE,
                "r",
                encoding="utf-8"
            ) as file:

                encrypted_payload = file.read()

            decrypted_json = decrypt_value(
                encrypted_payload
            )

            loaded_accounts = json.loads(
                decrypted_json
            )

        except Exception as error:

            raise RuntimeError(
                f"Failed to load encrypted accounts: {error}"
            )

        if not isinstance(
            loaded_accounts,
            dict
        ):

            raise RuntimeError(
                "Encrypted account file must contain dictionary object."
            )

        self._accounts_by_username = loaded_accounts

        logger.info(
            "[AccountRuntime] Loaded encrypted accounts from disk."
        )

    # =====================================================
    # INTEGRITY VERIFICATION
    # =====================================================

    async def _verify_integrity_of_loaded_accounts(
        self
    ):
        """
        Strict startup integrity verification.

        Hard Requirements
        -----------------
        Every account MUST contain:
        - password_hash
        - time_secret_encrypted
        - role
        """

        for username, user in (
            self._accounts_by_username.items()
        ):

            if not isinstance(user, dict):

                raise RuntimeError(
                    f"Invalid account object for user: {username}"
                )

            required_fields = {
                "password_hash",
                "time_secret_encrypted",
                "role",
            }

            missing_fields = []

            for field in required_fields:

                if field not in user:
                    missing_fields.append(field)

            if missing_fields:

                raise RuntimeError(
                    f"Account integrity failure for {username}: "
                    f"missing fields {missing_fields}"
                )

        logger.info(
            "[AccountRuntime] Account integrity verification passed."
        )

    def _cleanup_expired_pending_setups(self):

        current_time = time.time()

        expired_tokens = []

        for token, pending in (
            self._pending_account_setups.items()
        ):

            if current_time > pending["expires_at"]:

                expired_tokens.append(token)

        for token in expired_tokens:

            self._pending_account_setups.pop(
                token,
                None
            )


    # =====================================================
    # CLEAN SHUTDOWN
    # =====================================================

    async def shutdown(self):
        """
        Graceful shutdown handler.
        """

        logger.info(
            "[AccountRuntime] Shutdown requested."
        )

        if self._background_queue_worker:

            self._background_queue_worker.cancel()

            try:
                await self._background_queue_worker

            except asyncio.CancelledError:
                pass

        logger.info(
            "[AccountRuntime] Shutdown complete."
        )


# =========================================================
# GLOBAL SINGLETON
# =========================================================

account_runtime = AccountRuntime()

# =========================================================
# OPTIONAL CONVENIENCE ACCESSORS
# These are intentionally thin wrappers so the rest of the
# codebase does not need to directly touch the singleton.
# =========================================================

async def initialize_account_runtime():
    """
    Startup helper used during FastAPI startup.

    Safe to call multiple times.
    """
    await account_runtime.initialize()


async def shutdown_account_runtime():
    """
    Graceful shutdown helper.

    Flushes pending writes before process exit.
    """
    await account_runtime.shutdown()
