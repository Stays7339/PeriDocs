# ==========================================
# core/nlp/crisis_recorder.py
# save-state updated 202512171453
# Atomic, multi-process safe AES-encrypted crisis record writer.
# Appends encrypted records to data/recorded_crises.json using atomic writes.
# ==========================================

from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Dict, Any
from filelock import FileLock
import tempfile

from core.nlp.embeddings import fernet  # your AES Fernet instance

DATA_DIR = Path(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data")))
CRISIS_FILE = DATA_DIR / "recorded_crises.json"
LOCK_FILE = CRISIS_FILE.with_suffix(".lock")


def append_crisis_record(record: Dict[str, Any]) -> None:
    """
    Append a single crisis record (dictionary) to recorded_crises.json.

    Each record is AES-encrypted at the top level.
    Features:
    - Multi-process safe via file lock.
    - Atomic writes via temp file + os.replace().
    - Creates file and directory if they do not exist.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Convert record to JSON string and encrypt
    json_text = json.dumps(record, ensure_ascii=False)
    encrypted_text = fernet.encrypt(json_text.encode("utf-8")).decode("utf-8")

    with FileLock(str(LOCK_FILE)):
        # Load existing data
        if CRISIS_FILE.exists():
            try:
                with CRISIS_FILE.open("r", encoding="utf-8") as fh:
                    data = json.load(fh)
                    if not isinstance(data, list):
                        data = []
            except Exception:
                data = []
        else:
            data = []

        # Append encrypted record
        data.append(encrypted_text)

        # Write atomically
        with tempfile.NamedTemporaryFile(
            "w",
            delete=False,
            dir=DATA_DIR,
            encoding="utf-8",
            prefix="recorded_crises_",
            suffix=".json.tmp",
        ) as tmp:
            json.dump(data, tmp, ensure_ascii=False, indent=2)
            tmp_path = Path(tmp.name)

        os.replace(tmp_path, CRISIS_FILE)


def load_crisis_records() -> list[Dict[str, Any]]:
    """
    Load and decrypt all crisis records.
    Returns a list of dictionaries.
    """
    if not CRISIS_FILE.exists():
        return []

    try:
        with CRISIS_FILE.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
            if not isinstance(data, list):
                return []
    except Exception:
        return []

    records = []
    for enc in data:
        try:
            decrypted = fernet.decrypt(enc.encode("utf-8")).decode("utf-8")
            record = json.loads(decrypted)
            records.append(record)
        except Exception:
            continue  # skip corrupted entries

    return records
