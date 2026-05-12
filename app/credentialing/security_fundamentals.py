# ==========================================
# app/credentialing/security_fundamentals.py
# save-state 2026-05-11T14:23:00-04:00
# ==========================================

import os
import time
import json
import base64
import hmac
import hashlib
import secrets
import pyotp

from pathlib import Path
from argon2 import PasswordHasher
from cryptography.fernet import Fernet
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

AES_KEY = os.environ.get("PERIDOCS_AES_KEY")
if not AES_KEY:
    raise RuntimeError("PERIDOCS_AES_KEY env variable not found")

fernet = Fernet(AES_KEY)

_password_hasher = PasswordHasher()

SESSION_TTL_SECONDS = 3600

# ----------------------------
# SESSION SYSTEM
# ----------------------------

def create_session(username: str) -> str:
    session_payload = {
        "username": username,
        "expires_at": time.time() + SESSION_TTL_SECONDS,
        "number_used_once": secrets.token_urlsafe(16)
    }

    raw = json.dumps(session_payload, sort_keys=True)

    signature = hmac.new(
        AES_KEY,
        raw.encode(),
        hashlib.sha256
    ).hexdigest()

    return base64.urlsafe_b64encode(
        (raw + "." + signature).encode()
    ).decode()


def verify_session(token: str) -> bool:
    try:
        decoded = base64.urlsafe_b64decode(token.encode()).decode()
        raw, signature = decoded.rsplit(".", 1)

        expected = hmac.new(
            AES_KEY,
            raw.encode(),
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(signature, expected):
            return False

        payload = json.loads(raw)

        if time.time() > payload["expires_at"]:
            return None

        return payload

    except Exception:
        return False


# ----------------------------
# TIME-BASED ONE-TIME CODE
# ----------------------------

def generate_time_code_secret():
    return pyotp.random_base32()


def verify_time_code(secret: str, code: str):
    totp = pyotp.TOTP(secret)
    return totp.verify(code, valid_window=1)


def hash_password(plain_password: str) -> str:
    """
    Converts a plain password into a secure irreversible fingerprint.
    """
    return _password_hasher.hash(plain_password)


def verify_password(stored_hash: str, provided_password: str) -> bool:
    """
    Checks whether a provided password matches the stored fingerprint.
    """
    try:
        return _password_hasher.verify(stored_hash, provided_password)
    except Exception:
        return False

def generate_cross_site_request_forgery_token():
    return secrets.token_urlsafe(32)

def encrypt_value(value: str) -> str:
    return fernet.encrypt(value.encode()).decode()


def decrypt_value(value: str) -> str:
    return fernet.decrypt(value.encode()).decode()