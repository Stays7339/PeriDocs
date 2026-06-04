# ==========================================
# app/credentialing/account_runtime.py
# save-state 2026-06-03T12:36-04:00
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
from fastapi import HTTPException

from app.credentialing.security_fundamentals import (
    encrypt_value,
    decrypt_value,
    hash_password,
    verify_password,
    generate_totp_code_secret,
    verify_totp_code,
    create_session,
    generate_cross_site_request_forgery_token
)

logger = logging.getLogger(__name__)

CREATE_ACCOUNT_EVENT = "create_account"
DELETE_ACCOUNT_EVENT = "delete_account"

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

    Architectural Rules
    ------------------
    Routes should NEVER directly mutate account files.

    All account changes MUST flow through:
        account_runtime

    # A successfully completed signup results in an authenticated session.
    # Signup completion is treated as an implicit login event.
    """

    def __init__(self):

        self._changes_waiting_to_be_saved: int = 0

        self._max_changes_before_save: int = 25  # batch size trigger

        self._max_seconds_without_save: float = 60.0  # safety durability trigger

        self._last_save_time: float = time.time()

        # -----------------------------------------
        # startup state
        # -----------------------------------------

        self._initialized = False

        #=====================================================
        # READ SNAPSHOT CACHE (NEW: replaces lock-protected reads)
        # =====================================================

        self._accounts_snapshot: Dict[str, Dict[str, Any]] = {}

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

        self._pending_account_signups = {}

        self._pending_signup_expiration_seconds = 600

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

            try:

                # =====================================================
                # 1. WAIT FOR EVENT (WITH IDLE TIMEOUT)
                # Without this, _should_save_to_disk() only runs on new writes
                # =====================================================
                try:

                    event = await asyncio.wait_for(
                        self._account_operation_queue.get(),
                        timeout=1.0 # in seconds
                    )

                except asyncio.TimeoutError:

                    # =================================================
                    # IDLE FLUSH PATH (NO EVENTS RECEIVED)
                    # =================================================
                    if self._should_save_to_disk():
                        await self._save_changes_if_needed()
                        """
                        every 1 second:
                        worker wakes up
                        finds no event
                        runs _should_save_to_disk()

                        If:

                        _changes_waiting_to_be_saved > 0
                        and _last_save_time is older than 60s

                        → it flushes anyway
                        """

                    continue

                # =====================================================
                # 2. PRE-MUTATION VALIDATION (AUTHORITATIVE BOUNDARY)
                # prevents race condition where two events both pass API validation
                # =====================================================

                try:

                    event_type = event.get("type")

                    if event_type == CREATE_ACCOUNT_EVENT:

                        username = event["username"]

                        if username in self._accounts_snapshot:
                            raise RuntimeError(
                                f"Username already exists: {username}"
                            )
                    elif event_type == DELETE_ACCOUNT_EVENT:

                        username = event["username"]

                        if username not in self._accounts_snapshot:

                            raise RuntimeError(
                                f"Cannot delete nonexistent account: {username}"
                            )

                    # =================================================
                    # 3. APPLY MUTATION
                    # =================================================
                    user_id = self._apply_event(event)
                    event["_result_user_id"] = user_id

                    # mark dirty
                    self._changes_waiting_to_be_saved += 1

                    # =================================================
                    # 4. EAGER FLUSH CHECK
                    # =================================================
                    if self._should_save_to_disk():
                        await self._save_changes_if_needed()

                except Exception as error:

                    # =================================================
                    # 5. ERROR PATH (LOG + PROPAGATE TO FRONTEND LATER)
                    # =================================================

                    logger.exception(
                        "[AccountRuntime] Queue operation failed: %s",
                        error
                    )

                    # IMPORTANT:
                    # This is where JS toast integration will later hook in.
                    # We re-raise so upstream can capture + forward.
                    raise

                finally:

                    self._account_operation_queue.task_done()

            except Exception as fatal_error:

                # =====================================================
                # 6. CATASTROPHIC WORKER SAFETY NET
                # =====================================================
                logger.exception(
                    "[AccountRuntime] Worker fatal error: %s",
                    fatal_error
                )

                # Prevent silent death of worker loop
                await asyncio.sleep(0.5)
                
    async def _save_changes_if_needed(self):
        """
        Writes in-memory account state to disk.
        """

        await self._persist_accounts_to_disk()

        self._changes_waiting_to_be_saved = 0
        self._last_save_time = time.time()

    async def enqueue_account_operation(
        self,
        event: Dict[str, Any]
    ):
        """
        Queue a mutation event
        """

        await self._account_operation_queue.put(event)

    # =====================================================
    # ACCOUNT CREATION
    # =====================================================


    async def get_pending_signup_snapshot(
        self,
        signup_token: str,
    ):
        """
        Returns safe copy of pending signup state.
        """

        pending = self._pending_account_signups.get(
            signup_token
        )

        if not pending:
            return None

        return copy.deepcopy(pending)

    
    async def begin_account_signup(
        self,
        *,
        username: str,
        password_hash: str,
    ):
        """
        Begins staged account signup.

        Account is NOT persisted yet.

        Flow:
        - generate TOTP secret
        - hold staged state in memory
        - require valid TOTP before persistence
        """

        if await self.system_has_accounts():
            # optional: later replace with invite system
            pass


        self._cleanup_expired_pending_signups()

        if username in self._accounts_snapshot:

            raise RuntimeError(
                "Username already exists."
            )

        expired_or_replaced_tokens = []

        for token, pending in (
            self._pending_account_signups.items()
        ):

            if pending["username"] == username:

                expired_or_replaced_tokens.append(token)

        for token in expired_or_replaced_tokens:

            self._pending_account_signups.pop(
                token,
                None
            )

        signup_token = secrets.token_urlsafe(32)
        # generates cryptographically random bytes

        generated_totp_secret = (
            generate_totp_code_secret()
        )

        self._pending_account_signups[
            signup_token
        ] = {

            "username":
                username,

            "password_hash":
                password_hash,

            "generated_totp_secret":
                generated_totp_secret,

            "created_at":
                time.time(),

            "expires_at":
                (
                    time.time()
                    + self._pending_signup_expiration_seconds
                ),
        }

        return {
            "signup_token":
                signup_token,

            "totp_secret":
                generated_totp_secret,
        }

    async def complete_account_signup(
        self,
        *,
        signup_token: str,
        totp_code: str,
    ):
        """
        Finalizes account signup ONLY after valid TOTP.
        """



        self._cleanup_expired_pending_signups()

        pending = self._pending_account_signups.get(
            signup_token
        )

        if not pending:

            raise HTTPException(
                status_code=401,
                detail="Invalid TOTP code"
            )

        if time.time() > pending["expires_at"]:

            self._pending_account_signups.pop(
                signup_token,
                None
            )

            raise HTTPException(
                status_code=401,
                detail="Singup token expired"
            )

        generated_totp_secret = (
            pending["generated_totp_secret"]
        )

        if not verify_totp_code(
            generated_totp_secret,
            totp_code
        ):

            raise HTTPException(
                status_code=401,
                detail="Invalid TOTP code"
            )

        username = pending["username"]
        
        
        generated_totp_secret = pending["generated_totp_secret"]

        password_hash = pending["password_hash"]

        signup_token_to_delete = signup_token

        await self.enqueue_account_operation({
            "type": CREATE_ACCOUNT_EVENT,
            "username": username,
            "password_hash": password_hash,
            "totp_secret": generated_totp_secret,
            "signup_token": signup_token_to_delete,
        })

        self._pending_account_signups.pop(signup_token, None)

        # wait for queue to process (important)
        await self._account_operation_queue.join()

        user_id = await self._get_user_id_by_username(username)

        session_token = create_session(user_id)
        csrf_token = generate_cross_site_request_forgery_token()

        return {
            "user_id": user_id,
            "username": username,
            "session_token": session_token,
            "csrf_token": csrf_token,
        }

    # =====================================================
    # ACCOUNT DELETION
    # =====================================================

    async def delete_account(
        self,
        *,
        user_id: str,
    ):
        """
        Queue account deletion.

        Runtime memory is authoritative.
        Disk persistence occurs later via normal flush rules.
        """

        await self.enqueue_account_operation({
            "type": DELETE_ACCOUNT_EVENT,
            "user_id": user_id,
        })


    # =====================================================
    # AUTHENTICATION
    # =====================================================

    async def authenticate_username_and_password(
        self,
        *,
        username: str,
        plaintext_password: str,
    ) -> bool:

        user = await self._get_user_object_by_username(username)

        if not user:
            return False

        return verify_password(
            user["password_hash"],
            plaintext_password
        )
    async def _get_user_object_by_username(self, username: str):
        for user in self._accounts_snapshot.values():
            if user.get("username") == username:
                return user
        return None

    async def _get_user_id_by_username(self, username: str):
        for uid, user in self._accounts_snapshot.items():
            if user.get("username") == username:
                return uid
        return None

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

        user = await self._get_user_object_by_username(username)

        if not user:
            return None

        encrypted_secret = user.get(
            "totp_secret_encrypted"
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

        for user in self._accounts_snapshot.values():

            if user.get("role") == "administrator":
                return True

        return False

    async def system_has_accounts(self) -> bool:

        return bool(self._accounts_snapshot)

    async def get_user_role(
        self,
        username: str
    ) -> Optional[str]:

       user = await self._get_user_object_by_username(username)

       if not user:
        return None

       return user.get("role")

    async def get_user_snapshot(
        self,
        user_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Returns deep copy of user state.

        Internal state MUST NEVER be exposed directly.
        """

        logger.debug("[get_user_snapshot()] ACCOUNT_RUNTIME_ID=%s", id(account_runtime))

        user = self._accounts_snapshot.get(user_id)

        if not user:
            return None

        return copy.deepcopy(user)

    async def get_all_accounts_snapshot(self):
        """
        Safe full snapshot export.
        """

        return copy.deepcopy(self._accounts_snapshot)

    # =====================================================
    # PERSISTENCE
    # =====================================================
    def _should_save_to_disk(self) -> bool:
        now = time.time()

        time_since_save = now - self._last_save_time

        # 1. batch rule (primary)
        if self._changes_waiting_to_be_saved >= self._max_changes_before_save:
            return True

        # 2. time safety rule (durability guarantee)
        if self._changes_waiting_to_be_saved > 0 and time_since_save >= self._max_seconds_without_save:
            return True

        # 3. backlog override (only for congestion protection)
        queue_size = self._account_operation_queue.qsize()

        if queue_size > 100 and self._changes_waiting_to_be_saved > 0:
            return True

        return False

    
    
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
            self._accounts_snapshot,
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

            self._accounts_snapshot = {}

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

        self._accounts_snapshot = copy.deepcopy(loaded_accounts)

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
        - totp_secret_encrypted
        - role
        """

        for username, user in (
            self._accounts_snapshot.items()
        ):

            if not isinstance(user, dict):

                raise RuntimeError(
                    f"Invalid account object for user: {username}"
                )

            try:
                decrypt_value(user["totp_secret_encrypted"])
            except Exception:
                raise RuntimeError(f"Corrupt encrypted secret for {username}")

            required_fields = {
                "password_hash",
                "totp_secret_encrypted",
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

    def _cleanup_expired_pending_signups(self):

        current_time = time.time()

        expired_tokens = []

        for token, pending in (
            self._pending_account_signups.items()
        ):

            if current_time > pending["expires_at"]:

                expired_tokens.append(token)

        for token in expired_tokens:

            self._pending_account_signups.pop(
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

        # wait until queued events are fully processed
        await self._account_operation_queue.join()

        # flush remaining unsaved mutations
        if self._changes_waiting_to_be_saved > 0:
            await self._persist_accounts_to_disk()

        if self._background_queue_worker:

            self._background_queue_worker.cancel()

            try:
                await self._background_queue_worker

            except asyncio.CancelledError:
                pass

        logger.info(
            "[AccountRuntime] Shutdown complete."
        )
    
    def _apply_event(
        self,
        event: Dict[str, Any]
    ) -> str:

        event_type = event.get("type")

        if event_type == CREATE_ACCOUNT_EVENT:
            user_id = secrets.token_hex(32)

            username = event["username"]

            is_first_account = not self._accounts_snapshot

            role = (
                "administrator"
                if is_first_account
                else "ordinary"
            )

            self._accounts_snapshot[user_id] = {
                "user_id": user_id,
                "username": username,
                "password_hash": event["password_hash"],
                "totp_secret_encrypted": encrypt_value(
                    event["totp_secret"]
                ),
                "role": role,
                "created_at": time.time(),
            }

            logger.info(
                "[AccountRuntime] Created %s account: %s",
                role,
                username
            )

            return user_id
        
        elif event_type == DELETE_ACCOUNT_EVENT:

            user_id = event["user_id"]

            deleted_user = self._accounts_snapshot.pop(
                user_id,
                None
            )

            if deleted_user is None:

                raise RuntimeError(
                    f"Account vanished during deletion: {user_id}"
                )

            logger.info(
                "[AccountRuntime] Deleted account: %s",
                user_id
            )

            return user_id

        else:

            raise RuntimeError(
                f"Unknown account event type: {event_type}"
            )


# =========================================================
# OPTIONAL CONVENIENCE ACCESSORS
# These are intentionally thin wrappers so the rest of the
# codebase does not need to directly touch the singleton.
# =========================================================

# ---------------------------------------------------------
# GLOBAL SINGLETON

account_runtime = AccountRuntime()

# ---------------------------------------------------------





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


