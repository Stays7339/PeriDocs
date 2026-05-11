# ==========================================
# app/credentialing/create_first_account.py
# save-state 2026-05-10T21:21:35-04:00
# ==========================================

import time
import json
import hashlib
import secrets
from app.credentialing.account_storage import load_accounts, save_accounts
from app.credentialing.security_fundamentals import (
    generate_time_code_secret,
    verify_time_code
)

BOOTSTRAP_STORE = {} 
"""
completely reset upon server restart, 
but the server is meant to work with just no more than uvicorn process
"""
USED_BOOTSTRAP_TOKENS = set()


def create_bootstrap_ticket(username: str):
    """
    Creates a single-use bootstrap ticket stored server-side.
    """

    ticket_id = secrets.token_urlsafe(32)

    temp_secret = generate_time_code_secret()

    BOOTSTRAP_STORE[ticket_id] = {
        "username": username,
        "temp_secret": temp_secret,
        "created_at": time.time(),
        "expires_at": time.time() + 600
    }

    return ticket_id, temp_secret


def verify_bootstrap_ticket(ticket_id: str):
    """
    Ensures:
    - ticket exists
    - not expired
    - not already used
    """

    if ticket_id in USED_BOOTSTRAP_TOKENS:
        raise Exception("Bootstrap ticket already used")

    entry = BOOTSTRAP_STORE.get(ticket_id)

    if not entry:
        raise Exception("Invalid bootstrap ticket")

    if time.time() > entry["expires_at"]:
        raise Exception("Bootstrap ticket expired")

    return entry


def consume_bootstrap_ticket(ticket_id: str):
    USED_BOOTSTRAP_TOKENS.add(ticket_id)
    BOOTSTRAP_STORE.pop(ticket_id, None)