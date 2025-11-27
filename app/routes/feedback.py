"""
app/routes/feedback.py

Handles feedback submission via "/feedback" POST route.
"""

from fastapi import Request
from fastapi.responses import JSONResponse
from datetime import datetime
from app.routes import app
from app.helpers.file_ops import load_data, save_data, ensure_feedback_file
from app.helpers.json_safe import json_safe
import hashlib
from pydantic import BaseModel

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
    """
    # Get the current feedback file for this 6-hour window
    feedback_file = ensure_feedback_file()

    # Get client IP address
    client_host = request.client.host if request.client else "unknown"
    ip_hash = hashlib.sha256(client_host.encode("utf-8")).hexdigest()

    entry = {
        "type": payload.type,
        "text": payload.feedback_text,
        "timestamp": datetime.utcnow().isoformat(),
        "ip_hash": ip_hash
    }

    # Load existing data, append, save
    data = load_data(feedback_file)
    data.append(entry)
    save_data(data, file_path=feedback_file)

    return JSONResponse({"status": "ok", "entry": json_safe(entry)})
