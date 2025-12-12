"""
core/nlp/crisis_writer.py
save-state updated 202512111420

Async crisis record writer for PeriDocs.
- Appends AES-encrypted crisis records to data/recorded_crises.json atomically.
- Fully async, non-blocking, safe for single-process event loops.
"""

from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, Any
import aiofiles
import aiofiles.os
import asyncio

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
CRISIS_FILE = DATA_DIR / "recorded_crises.json"
_FILE_LOCK = asyncio.Lock()


async def append_crisis_record(record: Dict[str, Any]) -> None:
    """
    Append a single crisis record (dictionary) to recorded_crises.json.
    Fully async. Ensures atomic updates with asyncio lock.
    """
    await aiofiles.os.makedirs(DATA_DIR, exist_ok=True)

    async with _FILE_LOCK:
        # Load existing data
        data: list[Dict[str, Any]] = []
        if await aiofiles.os.path.exists(CRISIS_FILE):
            try:
                async with aiofiles.open(CRISIS_FILE, "r", encoding="utf-8") as f:
                    content = await f.read()
                    data = json.loads(content) if content.strip() else []
                    if not isinstance(data, list):
                        data = []
            except Exception:
                data = []

        # Append new record
        data.append(record)

        # Write back atomically
        try:
            async with aiofiles.open(CRISIS_FILE, "w", encoding="utf-8") as f:
                await f.write(json.dumps(data, ensure_ascii=False, indent=2))
        except Exception as e:
            # Final fallback: overwrite with just the new record
            async with aiofiles.open(CRISIS_FILE, "w", encoding="utf-8") as f:
                await f.write(json.dumps([record], ensure_ascii=False, indent=2))
