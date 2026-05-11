# ==========================================
# app/credentialing/account_storage.py
# save-state 2026-05-10T15:18:40-04:00
# ==========================================

import os
import json
from pathlib import Path
from cryptography.fernet import Fernet

DATA_DIR = Path("PeriDocs/data")
ACCOUNT_FILE = DATA_DIR / "accounts" / "accounts.json.enc"

ACCOUNT_FILE.parent.mkdir(parents=True, exist_ok=True)

MASTER_KEY = os.environ["PERIDOCS_AES_KEY"]
fernet = Fernet(MASTER_KEY)

_cache = None


def load_accounts():
    global _cache
    if _cache is not None:
        return _cache

    if not ACCOUNT_FILE.exists():
        _cache = {}
        return _cache

    raw = ACCOUNT_FILE.read_bytes()
    decrypted = fernet.decrypt(raw)
    _cache = json.loads(decrypted.decode())
    return _cache


def save_accounts(accounts: dict):
    global _cache
    _cache = accounts

    raw = json.dumps(accounts, sort_keys=True).encode()
    encrypted = fernet.encrypt(raw)

    ACCOUNT_FILE.write_bytes(encrypted)


def account_exists(username: str) -> bool:
    return username in load_accounts()