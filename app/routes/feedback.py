"""
app/routes/feedback.py

Handles feedback submission via "/feedback" POST route.
"""

from fastapi import Request, Form
from fastapi.responses import JSONResponse
from datetime import datetime
from app.routes import app
from app.helpers.file_ops import load_data, save_data, ensure_feedback_file
from app.helpers.json_safe import json_safe
import hashlib

# Path to feedback JSON data
FEEDBACK_FILE = "../data/feedback.json"


@app.post("/feedback", response_class=JSONResponse)
async def submit_feedback(
    request: Request,
    feedback_type: str = Form(...),
    feedback_text: str = Form(...)
):
    """
    Accepts user feedback:
    - Stores type, text, timestamp
    - Computes IP hash for anonymization
    - Ensures JSON-safe storage
    """
    ensure_feedback_file()

    # Get client IP address
    client_host = request.client.host if request.client else "unknown"
    ip_hash = hashlib.sha256(client_host.encode("utf-8")).hexdigest()

    entry = {
        "type": feedback_type,
        "text": feedback_text,
        "timestamp": datetime.utcnow().isoformat(),
        "ip_hash": ip_hash
    }

    save_data(entry, file_path=FEEDBACK_FILE)

    return JSONResponse({"status": "success", "entry": json_safe(entry)})
