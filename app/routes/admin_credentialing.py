# ==========================================
# app/routes/admin_credentialing.py
# save-state 2026-04-29T23:32:10-04:00
# ==========================================

import os
import json
import pyotp
import hmac
import hashlib
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


# ---------------------------------------------------
# SINGLE SOURCE OF TRUTH
# ---------------------------------------------------
_admin_cache = {}
_loaded = False


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
    """
    Create HMAC signature for a username
    """
    sig = hmac.new(
        AES_KEY.encode(),
        username.encode(),
        hashlib.sha256
    ).hexdigest()

    return f"{username}|{sig}"


def verify_session(cookie_value: str) -> bool:
    """
    Verify cookie has not been tampered with
    """
    try:
        username, sig = cookie_value.split("|")

        expected_sig = hmac.new(
            AES_KEY.encode(),
            username.encode(),
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(sig, expected_sig)
    except Exception:
        return False


# ---------------------------------------------------
# MODELS
# ---------------------------------------------------
class CreateAdminPayload(BaseModel):
    username: str
    password: str


class AdminLoginPayload(BaseModel):
    username: str
    password: str
    totp_code: str


# ---------------------------------------------------
# BOOTSTRAP + LOGIN PAGES
# ---------------------------------------------------
@router.get("/create", response_class=HTMLResponse)
async def create_page(request: Request):
    """
    CHANGE: prevents access if admins already exist
    """
    if has_admins():
        return RedirectResponse("/admin/auth/login")

    return templates.TemplateResponse("admin-bootstrap.html", {"request": request})


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """
    CHANGE: forces bootstrap if no admins exist yet
    """
    if not has_admins():
        return RedirectResponse("/admin/auth/create")

    return templates.TemplateResponse("admin-login.html", {"request": request})


# ---------------------------------------------------
# CREATE ADMIN
# ---------------------------------------------------
@router.post("/create-admin")
async def create_admin(payload: CreateAdminPayload):
    admins = load_admins()

    if payload.username in admins:
        raise HTTPException(status_code=400, detail="Admin already exists")

    # TOTP secret generated once
    totp_secret = pyotp.random_base32()

    admins[payload.username] = {
        "password_hash": ph.hash(payload.password),
        "totp_secret_enc": fernet.encrypt(totp_secret.encode()).decode(),
        "created_at": datetime.now(timezone.utc).isoformat()
    }

    save_admins()

    return {
        "status": "ok",
        "totp_secret": totp_secret
    }


# ---------------------------------------------------
# LOGIN
# ---------------------------------------------------
@router.post("/login")
async def login(payload: AdminLoginPayload):
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
        key="admin_session",
        value=session_value,
        httponly=True,
        secure=False,   # set True in production (HTTPS)
        samesite="lax"
    )

    return response

@router.post("/logout")
async def logout():
    response = JSONResponse({"status": "logged_out"})

    # NEW: delete cookie
    response.delete_cookie("admin_session")

    return response