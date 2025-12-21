# ==========================================
# core/nlp/crisis_recorder.py
# save-state updated 202512201520
# ==========================================

from __future__ import annotations
import os
from pathlib import Path
from typing import Dict, Any, List
from filelock import FileLock
import numpy as np
import json
import asyncio
import tempfile

from core.nlp.embeddings import fernet  # AES Fernet instance

DATA_DIR = Path(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data")))
CRISIS_FILE = DATA_DIR / "recorded_crises.npz"
LOCK_FILE = CRISIS_FILE.with_suffix(".lock")


def _encrypt_sensitive_fields(record: Dict[str, Any]) -> None:
    """Encrypts sensitive fields in-place under 'encrypted_sensitive'."""
    sensitive_fields = {k: record.pop(k) for k in ("text", "user_ip_hash") if k in record}
    if sensitive_fields:
        encrypted = fernet.encrypt(json.dumps(sensitive_fields, ensure_ascii=False).encode("utf-8"))
        record["encrypted_sensitive"] = encrypted


def _load_existing_records() -> List[Dict[str, Any]]:
    """Load existing records or raise if NPZ file is corrupted."""
    if not CRISIS_FILE.exists():
        return []
    try:
        with np.load(CRISIS_FILE, allow_pickle=True) as data:
            if "records" not in data:
                raise ValueError(f"{CRISIS_FILE} missing 'records' key; file may be corrupted")
            records = data["records"].tolist()
            if not isinstance(records, list):
                raise ValueError(f"{CRISIS_FILE} contents not a list; file may be corrupted")
            return records
    except Exception as e:
        raise RuntimeError(f"Failed to load {CRISIS_FILE}: {e}")


def _write_records_atomic(records: List[Dict[str, Any]]) -> None:
    """Write records atomically to NPZ file using tempfile to guarantee correct path."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=DATA_DIR,
        prefix=f"{CRISIS_FILE.stem}_",
        suffix=".npz",
        delete=False
    ) as tmp:
        tmp_path = Path(tmp.name)
        np.savez_compressed(tmp_path, records=np.array(records, dtype=object))
    os.replace(tmp_path, CRISIS_FILE)  # atomic move


def append_crisis_record(record: Dict[str, Any]) -> None:
    """
    Append a single crisis record to recorded_crises.npz.
    Sensitive fields are AES-encrypted.
    Metadata remains visible.
    Thread/process-safe via FileLock.
    """
    _encrypt_sensitive_fields(record)

    with FileLock(str(LOCK_FILE)):
        existing = _load_existing_records()
        existing.append(record)
        _write_records_atomic(existing)


async def append_crisis_record_async(record: Dict[str, Any]) -> None:
    """
    Async version for multiple concurrent users.
    Internally uses same FileLock to ensure atomic writes.
    """
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, append_crisis_record, record)


def load_crisis_records(decrypt_sensitive: bool = True) -> List[Dict[str, Any]]:
    """
    Load all crisis records.
    By default, decrypts sensitive fields (text, user_ip_hash).
    Raises RuntimeError if file is corrupted or decryption fails.
    """
    records = _load_existing_records()
    result = []

    for record in records:
        rec_copy = record.copy()
        if decrypt_sensitive and "encrypted_sensitive" in rec_copy:
            try:
                decrypted = fernet.decrypt(rec_copy.pop("encrypted_sensitive")).decode("utf-8")
                sensitive = json.loads(decrypted)
                rec_copy.update(sensitive)
            except Exception as e:
                raise RuntimeError(f"Failed to decrypt sensitive fields: {e}")
        result.append(rec_copy)

    return result
