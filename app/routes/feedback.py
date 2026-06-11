# ==========================================
# PeriDocs-code/app/routes/feedback.py
# save-state 2026-06-11T15:43-04:00 
# ==========================================

from fastapi import Request
from fastapi.responses import JSONResponse
from datetime import datetime
from app.routes import app
from app.helpers.file_ops import ensure_feedback_file
from app.helpers.json_safe import json_safe
import hashlib
from pydantic import BaseModel
import aiofiles
import aiofiles.os
import json
import os
import uuid

# ---------------------- Pydantic model ---------------------- #
class FeedbackPayload(BaseModel):
    feedback_text: str
    type: str
    ip_hash: str = "unknown"


@app.post("/feedback", response_class=JSONResponse)
async def submit_feedback_json(payload: FeedbackPayload, request: Request):
    """
    Accepts user feedback as JSON:
    - Stores type, text, timestamp
    - Computes IP hash for anonymization
    - Ensures JSON-safe storage
    Fully asynchronous (async I/O) to avoid blocking the server.
    Implements atomic async write to prevent partial JSON corruption.
    """
    # Get the current feedback file for this 6-hour window
    feedback_file = ensure_feedback_file()

    # Ensure directory exists
    os.makedirs(os.path.dirname(feedback_file), exist_ok=True)

    # Compute client IP hash
    client_host = request.client.host if request.client else "unknown"
    ip_hash = hashlib.sha256(client_host.encode("utf-8")).hexdigest()

    entry_for_feedback = {
        "type": payload.type,
        "text": payload.feedback_text,
        "timestamp": datetime.utcnow().isoformat(),
        "ip_hash": ip_hash
    }

    # --- Async load safely ---
    try:
        async with aiofiles.open(feedback_file, mode="r", encoding="utf-8") as f:
            content = await f.read()
            data = json.loads(content) if content.strip() else []
    except (FileNotFoundError, json.JSONDecodeError):
        data = []

    # Append new entry
    data.append(entry_for_feedback)

    # --- Async atomic save with unique tmp ---
    tmp_file_path = f"{feedback_file}.{uuid.uuid4().hex}.tmp"
    async with aiofiles.open(tmp_file_path, mode="w", encoding="utf-8") as tmp:
        await tmp.write(json.dumps(json_safe(data), ensure_ascii=False, indent=2))

    await aiofiles.os.replace(tmp_file_path, feedback_file)

    return JSONResponse({"status": "ok", "entry": json_safe(entry_for_feedback)})
