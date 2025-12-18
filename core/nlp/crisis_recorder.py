# ==========================================
# core/nlp/crisis_recorder.py
# save-state 202512172036
# Atomic, multi-process safe AES-encrypted crisis record writer.
# Stores sensitive fields (text, user_ip_hash) encrypted in data/recorded_crises.npz.
# All other metadata remains visible.
# ==========================================

from __future__ import annotations
import os
from pathlib import Path
from typing import Dict, Any
from filelock import FileLock
import tempfile
import numpy as np
import json

from core.nlp.embeddings import fernet  # your AES Fernet instance

DATA_DIR = Path(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data")))
CRISIS_FILE = DATA_DIR / "recorded_crises.npz"
LOCK_FILE = CRISIS_FILE.with_suffix(".lock")


def append_crisis_record(record: Dict[str, Any]) -> None:
    """
    Append a single crisis record to recorded_crises.npz.
    Sensitive fields (text, user_ip_hash) are AES-encrypted.
    Metadata remains visible.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Split sensitive fields from metadata
    sensitive_fields = {}
    for key in ("text", "user_ip_hash"):
        if key in record:
            sensitive_fields[key] = record.pop(key)

    # Encrypt sensitive fields
    if sensitive_fields:
        encrypted_sensitive = fernet.encrypt(json.dumps(sensitive_fields, ensure_ascii=False).encode("utf-8"))
        record["encrypted_sensitive"] = encrypted_sensitive

    with FileLock(str(LOCK_FILE)):
        # Load existing records
        if CRISIS_FILE.exists():
            try:
                with np.load(CRISIS_FILE, allow_pickle=True) as data:
                    existing = data["records"].tolist()
            except Exception:
                existing = []
        else:
            existing = []

        # Append new record
        existing.append(record)

        # Write atomically
        with tempfile.NamedTemporaryFile(
            delete=False,
            dir=DATA_DIR,
            prefix="recorded_crises_",
            suffix=".npz.tmp",
        ) as tmp:
            tmp_path = Path(tmp.name)
            np.savez_compressed(tmp_path, records=np.array(existing, dtype=object))

        os.replace(tmp_path, CRISIS_FILE)


def load_crisis_records(decrypt_sensitive: bool = True) -> list[Dict[str, Any]]:
    """
    Load all crisis records.
    By default, decrypts sensitive fields (text, user_ip_hash).
    Set decrypt_sensitive=False to leave them encrypted.
    """
    if not CRISIS_FILE.exists():
        return []

    try:
        with np.load(CRISIS_FILE, allow_pickle=True) as data:
            records = data["records"].tolist()
    except Exception:
        return []

    result = []
    for record in records:
        rec_copy = record.copy()
        if decrypt_sensitive and "encrypted_sensitive" in rec_copy:
            try:
                decrypted = fernet.decrypt(rec_copy.pop("encrypted_sensitive")).decode("utf-8")
                sensitive = json.loads(decrypted)
                rec_copy.update(sensitive)
            except Exception:
                pass  # leave encrypted if decryption fails
        result.append(rec_copy)

    return result
