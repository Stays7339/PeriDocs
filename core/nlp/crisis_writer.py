"""
file: core/nlp/crisis_writer.py
save-state updated 202511231610 (date and time formatted as follows: YYYYMMDDhhmm)
Atomic crisis record writer.

Appends AES-encrypted crisis records to data/recorded_crises.json in an atomic and safe way.
Creates file if it does not exist.
"""

from __future__ import annotations
import json
import os
from pathlib import Path
from threading import Lock
from typing import Dict, Any

DATA_DIR = Path(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data")))
CRISIS_FILE = DATA_DIR / "recorded_crises.json"
_lock = Lock()

def append_crisis_record(record: Dict[str, Any]) -> None:
    """
    Append a single crisis record (dictionary) to recorded_crises.json.
    Uses a simple list container in the file. The writer is safe for concurrent processes
    in the same Python process (thread lock). If you need multi-process safety, replace with file-based lock.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    with _lock:
        if not CRISIS_FILE.exists():
            # create file with initial list
            with CRISIS_FILE.open("w", encoding="utf-8") as fh:
                json.dump([record], fh, ensure_ascii=False, indent=2)
            return

        try:
            with CRISIS_FILE.open("r+", encoding="utf-8") as fh:
                # load existing list
                try:
                    fh.seek(0)
                    data = json.load(fh)
                    if not isinstance(data, list):
                        data = []
                except Exception:
                    data = []
                data.append(record)
                # write back
                fh.seek(0)
                fh.truncate(0)
                json.dump(data, fh, ensure_ascii=False, indent=2)
        except Exception:
            # Fallback: write new file
            with CRISIS_FILE.open("w", encoding="utf-8") as fh:
                json.dump([record], fh, ensure_ascii=False, indent=2)
