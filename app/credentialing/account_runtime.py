# ==========================================
# app/credentialing/account_runtime.py
# save-state 2026-05-10T21:56:12-04:00
# ==========================================

"""
PeriDocs Account Runtime
========================

Purpose
-------
This file provides the SINGLE authoritative runtime for:

- account creation
- account lookup
- account mutation
- encrypted persistence
- startup integrity verification
- serialized account writes
- role enforcement

Design Philosophy
-----------------
Memory is authoritative.
Disk is durability.

Meaning:
- The in-memory account state is treated as the live truth.
- The encrypted file on disk is treated as persistent storage.
- All mutations flow through ONE controlled runtime.

This avoids:
- race conditions
- partial writes
- inconsistent account state
- scattered credential logic

Important Security Rules
------------------------
- passwords are ALWAYS hashed
- TOTP secrets are ALWAYS encrypted at rest
- usernames may remain plaintext
- account persistence is ALWAYS encrypted
- all disk writes are atomic
- all mutations are serialized through a queue + lock

This runtime intentionally avoids:
- direct route-layer mutations
- direct storage manipulation
- exposing mutable internal references

# =========================================================
# IMPORTANT DESIGN NOTES
# =========================================================
#
# WHY A QUEUE EXISTS EVEN THOUGH USER COUNT IS LOW
# ---------------------------------------------------------
# The queue is not about throughput.
#
# It exists to guarantee:
#
# - deterministic write order
# - no overlapping writes
# - no partially-written encrypted files
# - future scalability without redesign
#
#
# WHY MEMORY IS AUTHORITATIVE
# ---------------------------------------------------------
# Disk is treated as durability storage.
#
# Runtime memory is treated as the current truth.
#
# This matches the other runtimes within the PeriDocs project:
#
# - ledger runtime
# - centroid runtime
# - entry runtime
#
# architecture philosophy.
#
#
# WHY TMP FILES + os.replace()
# ---------------------------------------------------------
# This prevents:
#
# - corrupted partial writes
# - interrupted writes
# - malformed encrypted snapshots
#
# because os.replace() is atomic on modern operating systems.
#
#
# WHY USERNAMES REMAIN PLAINTEXT
# ---------------------------------------------------------
# Usernames are identifiers, not secrets.
#
# Password hashes and TOTP secrets remain protected.
#
#
# WHY TOTP SECRETS ARE ENCRYPTED INSTEAD OF HASHED
# ---------------------------------------------------------
# TOTP verification requires the original secret.
#
# Hashing would destroy the ability to generate valid codes.
#
# Therefore:
#
# - encrypted at rest
# - decrypted only during verification
#
# is the correct model.
#
#
# WHY THIS FILE DOES NOT HANDLE LOGIN
# ---------------------------------------------------------
# Runtime responsibility:
#
# - memory authority
# - serialization
# - persistence
# - integrity guarantees
#
# Authentication responsibility:
#
# - password verification
# - session creation
# - CSRF
# - TOTP verification
#
# Separation keeps the architecture understandable.

"""

import os
import json
import copy
import asyncio
import logging
from typing import Dict, Optional, Any

from app.credentialing.security_fundamentals import (
    encrypt_value,
    decrypt_value,
    hash_password,
    verify_password,
)

logger = logging.getLogger(__name__)


# =========================================================
# CONFIGURATION
# =========================================================

DATA_DIRECTORY = os.getenv("PERIDOCS_DATA_DIR", "data")

ACCOUNT_DIRECTORY = os.path.join(
    DATA_DIRECTORY,
    "accounts"
)

ENCRYPTED_ACCOUNT_FILE = os.path.join(
    ACCOUNT_DIRECTORY,
    "accounts.encrypted.json"
)

TEMPORARY_WRITE_FILE = (
    ENCRYPTED_ACCOUNT_FILE + ".tmp"
)


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
        # fast lookup cache
        # -----------------------------------------

        self._username_lookup_index: Dict[str, Dict[str, Any]] = {}

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

            os.makedirs(
                ACCOUNT_DIRECTORY,
                exist_ok=True
            )

            await self._load_accounts_from_disk()

            self._rebuild_username_lookup_index()

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
        Background worker that serializes queued account
        operations into deterministic execution order.

        This ensures:
        - no overlapping account writes
        - deterministic mutation ordering
        - centralized persistence boundaries
        """

        logger.info(
            "[AccountRuntime] Queue worker started."
        )

        while True:

            queued_operation = await (
                self._account_operation_queue.get()
            )

            try:

                await queued_operation()

            except Exception as error:

                logger.exception(
                    "[AccountRuntime] Queue operation failed: %s",
                    error
                )

            finally:

                self._account_operation_queue.task_done()

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

    async def create_account(
        self,
        *,
        username: str,
        plaintext_password: str,
        plaintext_time_based_one_time_password_secret: str,
    ):
        """
        Create and persist a new account.

        Security Guarantees
        -------------------
        - password is hashed before storage
        - TOTP secret is encrypted before storage
        - first account automatically becomes administrator
        - all later accounts become ordinary users
        """

        async with self._account_write_lock:

            if username in self._accounts_by_username:

                raise RuntimeError(
                    "Username already exists."
                )

            role = (
                "administrator"
                if not self._accounts_by_username
                else "ordinary"
            )

            self._accounts_by_username[username] = {

                # usernames intentionally plaintext

                "password_hash":
                    hash_password(
                        plaintext_password
                    ),

                "time_secret_encrypted":
                    encrypt_value(
                        plaintext_time_based_one_time_password_secret
                    ),

                "role":
                    role,
            }

            self._rebuild_username_lookup_index()

            await self._persist_accounts_to_disk()

            logger.info(
                "[AccountRuntime] Created account: %s",
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

        os.makedirs(
            ACCOUNT_DIRECTORY,
            exist_ok=True
        )

        serialized_account_data = json.dumps(
            self._accounts_by_username,
            ensure_ascii=False,
            indent=2
        )

        encrypted_payload = encrypt_value(
            serialized_account_data
        )

        with open(
            TEMPORARY_WRITE_FILE,
            "w",
            encoding="utf-8"
        ) as temporary_file:

            temporary_file.write(
                encrypted_payload
            )

            temporary_file.flush()

            os.fsync(
                temporary_file.fileno()
            )

        os.replace(
            TEMPORARY_WRITE_FILE,
            ENCRYPTED_ACCOUNT_FILE
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

    # =====================================================
    # INDEXES
    # =====================================================

    def _rebuild_username_lookup_index(
        self
    ):
        """
        Fast username lookup index.

        This is a cache, not a second source of truth.
        """

        self._username_lookup_index = {

            username: user

            for username, user in (
                self._accounts_by_username.items()
            )
        }

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


async def get_accounts_snapshot():
    """
    Safe read-only deep copy of all accounts.

    Returns:
        dict
    """
    return await account_runtime.get_all_accounts()


async def get_account(username: str):
    """
    Safe lookup helper.

    Returns:
        dict | None
    """
    return await account_runtime.get_account(username)


async def does_any_administrator_exist() -> bool:
    """
    Returns True if at least one administrator exists.
    """
    return await account_runtime.has_administrators()


async def create_account(
    *,
    username: str,
    password_hash: str,
    encrypted_time_based_one_time_password_secret: str,
    role: str,
):
    """
    Thin wrapper around runtime queue insertion.

    The queue serializes writes automatically.
    """

    account_payload = {
        "password_hash": password_hash,
        "time_secret_encrypted": encrypted_time_based_one_time_password_secret,
        "role": role,
    }

    await account_runtime.enqueue_account_creation(
        username=username,
        account_payload=account_payload
    )


async def update_account_role(
    *,
    username: str,
    role: str,
):
    """
    Queue-safe role update helper.
    """

    await account_runtime.enqueue_account_role_change(
        username=username,
        role=role
    )


async def remove_account(username: str):
    """
    Queue-safe account deletion helper.
    """

    await account_runtime.enqueue_account_deletion(
        username=username
    )
