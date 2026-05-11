# ==========================================
# app/routes/admin_credentialing.py
# save-state 2026-05-10T14:00:00-04:00
# ==========================================

import os
import json
import pyotp
import hmac
import hashlib
import time
import hmac
import base64
import secrets

from collections import defaultdict
from fastapi import Request
from datetime import datetime, timezone
from pathlib import Path


from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from argon2 import PasswordHasher
from cryptography.fernet import Fernet
from dotenv import load_dotenv

# ---------------------------------------------------
# CONFIG
# ---------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = os.getenv("PERIDOCS_DATA_DIR", "data")

ADMIN_FILE = os.path.join(DATA_DIR, "logins", "admins.json.enc")
os.makedirs(os.path.dirname(ADMIN_FILE), exist_ok=True)

load_dotenv(PROJECT_ROOT / ".env")

AES_KEY = os.environ.get("PERIDOCS_AES_KEY")
if not AES_KEY:
    raise RuntimeError("PERIDOCS_AES_KEY env variable not set")

fernet = Fernet(AES_KEY)
ph = PasswordHasher()

router = APIRouter(prefix="/admin/auth", tags=["admin-auth"])
templates = Jinja2Templates(directory="app/templates")
templates.env.globals["ProductionMode"] = ProductionMode # for making changes easier between Dev mode and Produciton mode


# ---------------------------------------------------
# SINGLE SOURCE OF TRUTH
# ---------------------------------------------------

BOOTSTRAP_SECRET = AES_KEY  # reuse master Fernet key

BOOTSTRAP_TTL_SECONDS = 600  # 10 minutes validity window

RATE_LIMIT_STORE = defaultdict(list)

RATE_LIMIT_WINDOW_SECONDS = 60
RATE_LIMIT_MAX_REQUESTS = 10

SESSION_TTL = 3600  # 1 hour

BOOTSTRAP_STORE = {}

BOOTSTRAP_IN_PROGRESS = False


_admin_cache = {}
_loaded = False

# Stateless bootstrap system (no server memory state)
# token = signed payload (username, password, secret, expiry)


def load_admins():
    """
    ONLY canonical admin state loader.
    Everything else derives from this.
    """
    global _admin_cache, _loaded

    if _loaded:
        return _admin_cache

    if not os.path.exists(ADMIN_FILE):
        _admin_cache = {}
        _loaded = True
        return _admin_cache

    with open(ADMIN_FILE, "rb") as f:
        decrypted = fernet.decrypt(f.read())
        _admin_cache = json.loads(decrypted.decode())

    _loaded = True
    return _admin_cache


def save_admins():
    """
    Writes encrypted admin DB.
    """
    global _admin_cache

    raw = json.dumps(_admin_cache).encode()
    encrypted = fernet.encrypt(raw)

    with open(ADMIN_FILE, "wb") as f:
        f.write(encrypted)


def has_admins() -> bool:
    """
    CLEAN truth check (replaces ALL admin_exists variants)
    Now derived from decrypted state, not file size
    """
    return len(load_admins()) > 0

def sign_session(username: str) -> str:
    payload = {
        "username": username,
        "exp": time.time() + SESSION_TTL,
        "number-used-once": secrets.token_urlsafe(16)
    }

    raw = json.dumps(payload, sort_keys=True)

    sig = hmac.new(
        AES_KEY.encode(),
        raw.encode(),
        hashlib.sha256
    ).hexdigest()

    return base64.urlsafe_b64encode(
        (raw + "." + sig).encode()
    ).decode()


def verify_session(cookie_value: str) -> bool:
    try:
        decoded = base64.urlsafe_b64decode(cookie_value.encode()).decode()

        raw, sig = decoded.rsplit(".", 1)

        expected = hmac.new(
            AES_KEY.encode(),
            raw.encode(),
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(sig, expected):
            return False

        payload = json.loads(raw)

        if time.time() > payload["exp"]:
            return False

        return True

    except Exception:
        return False


# ---------------------------------------------------
# MODELS
# ---------------------------------------------------
class CreateAdminPayload(BaseModel):
    username: str

class CompleteBootstrapPayload(BaseModel):
    username: str
    temp_secret: str
    totp_code: str

class AdminLoginPayload(BaseModel):
    username: str
    totp_code: str


# ---------------------------------------------------
# BOOTSTRAP + LOGIN PAGES
# ---------------------------------------------------
@router.get("/create", response_class=HTMLResponse)
async def create_page(request: Request):
    """
    prevents access if admins already exist
    """

    global BOOTSTRAP_IN_PROGRESS

    if BOOTSTRAP_IN_PROGRESS:
        raise HTTPException(status_code=409, detail="Bootstrap already in progress")

    BOOTSTRAP_IN_PROGRESS = True

    if has_admins():
        return RedirectResponse("/admin/auth/login")

    return templates.TemplateResponse("admin-bootstrap.html", {"request": request})


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """
   forces bootstrap if no admins exist yet
    """
    if not has_admins():
        return RedirectResponse("/admin/auth/create")

    return templates.TemplateResponse("admin-login.html", {"request": request})


# ---------------------------------------------------
# BEGIN BOOTSTRAP
# ---------------------------------------------------
@router.post("/create-account")
async def create_identity(payload: CreateAdminPayload):

    if not rate_limit(f"bootstrap:create:{payload.username}"):
        raise HTTPException(status_code=429, detail="Too many requests")

    if not rate_limit(f"login:{payload.username}"):
        raise HTTPException(status_code=429, detail="Too many requests")

    if has_admins():
        raise HTTPException(status_code=403, detail="Identity already initialized")

    totp_secret = pyotp.random_base32()

    bootstrap_token = create_bootstrap_token({
        "username": payload.username,
        "temp_secret": totp_secret,
        "role": "user",
        "created_at": time.time(),
        "expires_at": time.time() + BOOTSTRAP_TTL_SECONDS
    })
    return {
        "status": "pending",
        "bootstrap_token": bootstrap_token,
        "totp_secret": totp_secret
    }

# ---------------------------------------------------
# COMPLETE BOOTSTRAP
# ---------------------------------------------------
@router.post("/complete-bootstrap")
async def complete_identity_setup(payload: dict):
    if not rate_limit(f"bootstrap:create:{payload.username}"):
        raise HTTPException(status_code=429, detail="Too many requests")

    if not rate_limit(f"login:{payload.username}"):
        raise HTTPException(status_code=429, detail="Too many requests")

    token_data = _verify_bootstrap_token(payload["bootstrap_token"])

    totp = pyotp.TOTP(token_data["temp_secret"])

    if not totp.verify(payload["totp_code"], valid_window=1):
        raise HTTPException(status_code=401, detail="Invalid TOTP")

    token_hash = hashlib.sha256(payload["bootstrap_token"].encode()).hexdigest()

    BOOTSTRAP_STORE[token_hash]["used"] = True

    "password_hash": ph.hash(payload.password),
    token_data = verify_bootstrap_token(payload.bootstrap_token)

    identities = load_admins()

    # identity system (admin is just a role flag)
    identities[token_data["username"]] = {
        "password_hash": ph.hash(token_data["password"]),
        "totp_secret_enc": fernet.encrypt(
            token_data["temp_secret"].encode()
        ).decode(),
        "role": token_data["role"],  # ADMIN, USER, etc.
        "created_at": datetime.now(timezone.utc).isoformat()
    }

    save_admins()

    BOOTSTRAP_IN_PROGRESS = False

    return {"status": "ok"}


@router.post("/reset-bootstrap")
async def reset_bootstrap():

    global _bootstrap_session

    _bootstrap_session = None

    BOOTSTRAP_IN_PROGRESS = False
    BOOTSTRAP_STORE.clear()

    return {"status": "reset"}

# ---------------------------------------------------
# LOGIN
# ---------------------------------------------------
@router.post("/login")
async def login(payload: AdminLoginPayload):

    if not rate_limit(f"bootstrap:create:{payload.username}"):
        raise HTTPException(status_code=429, detail="Too many requests")

    if not rate_limit(f"login:{payload.username}"):
        raise HTTPException(status_code=429, detail="Too many requests")

    admins = load_admins()

    admin = admins.get(payload.username)
    if not admin:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    try:
        ph.verify(admin["password_hash"], payload.password)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    totp_secret = fernet.decrypt(admin["totp_secret_enc"].encode()).decode()
    totp = pyotp.TOTP(totp_secret)

    if not totp.verify(payload.totp_code, valid_window=1):
        raise HTTPException(status_code=401, detail="Invalid TOTP")

    # issue session cookie
    response = JSONResponse({"status": "ok"})

    session_value = sign_session(payload.username)

    response.set_cookie(
        key="session",
        value=session_value,
        httponly=True,
        secure=ProductionMode,
        samesite="strict"
    )

    return response

@router.post("/logout")
async def logout():

    if not rate_limit(f"bootstrap:create:{payload.username}"):
        raise HTTPException(status_code=429, detail="Too many requests")

    if not rate_limit(f"login:{payload.username}"):
        raise HTTPException(status_code=429, detail="Too many requests")

    response = JSONResponse({"status": "logged_out"})

    # NEW: delete cookie
    response.delete_cookie("session")

    return response

def _sign_bootstrap_payload(payload: dict) -> str:
    """
    Creates tamper-proof bootstrap token (stateless session)
    """

    raw = json.dumps(payload, sort_keys=True).encode()

    sig = hmac.new(
        BOOTSTRAP_SECRET.encode(),
        raw,
        hashlib.sha256
    ).hexdigest()

    return base64.urlsafe_b64encode(raw + b"." + sig.encode()).decode()


def verify_bootstrap_token(token: str) -> dict:
    token_hash = hashlib.sha256(token.encode()).hexdigest()

    entry = BOOTSTRAP_STORE.get(token_hash)

    if not entry:
        raise HTTPException(status_code=401, detail="Invalid bootstrap token")

    if entry["used"]:
        raise HTTPException(status_code=401, detail="Bootstrap token already used")

    payload = entry["payload"]

    if time.time() > payload["expires_at"]:
        raise HTTPException(status_code=401, detail="Bootstrap token expired")

    return payload


def rate_limit(key: str):
    """
    Simple sliding window rate limiter (in-memory).
    """
    now = time.time()

    window = RATE_LIMIT_STORE[key]

    # remove expired timestamps
    RATE_LIMIT_STORE[key] = [
        t for t in window if now - t < RATE_LIMIT_WINDOW_SECONDS
    ]

    if len(RATE_LIMIT_STORE[key]) >= RATE_LIMIT_MAX_REQUESTS:
        return False

    RATE_LIMIT_STORE[key].append(now)
    return True

def create_bootstrap_token(payload: dict) -> str:
    """
    Stateless-safe token:
    - JSON encoded
    - hashed key lookup
    """
    raw = json.dumps(payload, sort_keys=True).encode()

    token_id = secrets.token_urlsafe(32)

    token_hash = hashlib.sha256(token_id.encode()).hexdigest()

    BOOTSTRAP_STORE[token_hash] = {
        "payload": payload,
        "used": False
    }

    return token_id

@router.post("/restart-bootstrap")
async def restart_bootstrap():
    global BOOTSTRAP_IN_PROGRESS

    BOOTSTRAP_IN_PROGRESS = False
    BOOTSTRAP_STORE.clear()

    return {"status": "reset"}