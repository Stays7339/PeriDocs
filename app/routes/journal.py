"""
PeriDocs-code/app/routes/journal.py
Save-state: 20251212XXXX
Journal Submission and Display Routes for PeriDocs
---------------------------------------------------

Handles:
- Journal submission (form + JSON)
- NLP processing (embedding-only emotion analysis)
- Direct storage of journal entries (no pruning or sentiment)
- Embedding backups
- Display of submission results
- Preloads persistent candidate emotions on startup
"""

from fastapi import Request, Body
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime
from pathlib import Path
from glob import glob
import json
import asyncio

from app.routes import app
from app.helpers.file_ops import load_data, append_entry
from core.nlp.process_entry import process_entry_async, get_top_matches
from core.nlp.emotion_analysis import normalize_emotion_profile
from core.nlp import repetition_score
from core.nlp.pii import redact_pii
from core.nlp import emotion_model

# ------------------------------
# Templates
# ------------------------------
templates = Jinja2Templates(directory="app/templates")

# ------------------------------
# File paths
# ------------------------------
JOURNALS_FILE = "data/journals.json"

# 6-hour backup window for embeddings
now = datetime.now()
window = now.hour // 6  # 0: 00-05, 1: 06-11, 2: 12-17, 3: 18-23
BACKUP_TIMESTAMP = now.strftime("%Y%m%d") + f"_{window}"
JOURNALS_EMBED_FILE = f"data/journals_embeddings_dump{BACKUP_TIMESTAMP}.json"

# Load all embeddings files into index
embeddings_index = {}
for path_str in sorted(glob("data/journals_embeddings_dump*.json")):
    path = Path(path_str)
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                embeddings_index.update(data)
        except Exception as e:
            print(f"Warning: failed to load {path}: {e}")

# ------------------------------
# Preload persistent candidate emotions on startup
# ------------------------------
@app.on_event("startup")
async def preload_candidate_emotions():
    await emotion_model.load_existing_candidates()
    print(f">>>> Loaded {emotion_model._PENDING_CANDIDATES} pending candidate emotions")


# ---------- Submit Journal Entry ----------
@app.post("/submit", response_class=HTMLResponse)
async def submit_journal(
    request: Request,
    entry_text: str = Body(..., embed=True)
):
    """
    Endpoint to submit a journal entry.
    """
    if not entry_text:
        form = await request.form()
        entry_text = form.get("entry_text", "")

    client_host = request.client.host if request.client else "127.0.0.1"

    # ----------------------
    # PII REDACTION
    # ----------------------
    entry_text_safe = redact_pii(entry_text, redact_names=False)

    # ----------------------
    # NLP PROCESSING
    # ----------------------
    nlp_result = await process_entry_async(entry_text_safe, user_ip=client_host)

    # Normalize emotions
    emotions_data = nlp_result.get("emotions") or {}
    nlp_result["emotions"] = normalize_emotion_profile(emotions_data)

    # Safe entities conversion
    if nlp_result.get("entities"):
        nlp_result["entities"] = [
            str({"text": e.get("text", ""), "label": e.get("label", "")})
            for e in nlp_result["entities"]
        ]

    nlp_result["text"] = entry_text_safe

    # ----------------------
    # Directly store entry
    # ----------------------
    entry_to_store = {
        "id": nlp_result.get("sha8") or nlp_result.get("id"),
        "safe_text": entry_text_safe,
        "timestamp": datetime.utcnow().isoformat(),
        "nlp": nlp_result,
        "embedding": f"stored in {JOURNALS_EMBED_FILE}"
    }
    append_entry(entry_to_store, JOURNALS_FILE)

    # ----------------------
    # Decide response type
    # ----------------------
    content_type = request.headers.get("content-type", "")
    is_json_request = content_type.startswith("application/json")

    if is_json_request:
        return JSONResponse({
            "message": "Journal submitted successfully",
            "nlp_result": nlp_result
        })
    else:
        return RedirectResponse(f"/submit-success?id={entry_to_store['id']}", status_code=303)

# ---------- Submit Success ----------
@app.get("/submit-success", response_class=HTMLResponse)
async def submit_success(request: Request, id: str):
    """
    Display submission success.
    """
    all_entries = load_data(JOURNALS_FILE)
    entry = next((e for e in all_entries if isinstance(e, dict) and e.get("id") == id), None)
    if entry is None:
        return templates.TemplateResponse(
            "submit-success.html", {"request": request, "error": "Entry not found."}
        )

    # Get entry vector and compute top matches
    entry_vec = embeddings_index.get(entry.get("sha8", entry["id"]))
    top_matches = []
    total_sim = 0.0
    if entry_vec:
        top_match_ids = get_top_matches(entry_vec, embeddings_index, top_n=20)
        for eid, sim in top_match_ids:
            if eid == entry.get("id"):
                continue
            match_entry = next((e for e in all_entries if e.get("id") == eid), None)
            if match_entry:
                sim_clipped = min(max(sim, 0.0), 1.0)
                similarity_pct = round(sim_clipped * 100, 1)
                total_sim += similarity_pct
                top_matches.append({
                    "entry_id": eid,
                    "excerpt": match_entry.get("safe_text", "")[:200],
                    "similarity_pct": similarity_pct
                })

    average_similarity_pct = round(total_sim / len(top_matches), 1) if top_matches else 0.0
    repetition_pct = repetition_score(entry.get("safe_text", ""))

    # Emotions
    emotions_data = entry.get("nlp", {}).get("emotions") or {}
    emotion_summary_display = ", ".join(
        f"{k.capitalize()}: {v*100:.1f}%" for k, v in emotions_data.items()
    )
    dominant_emotion = max(emotions_data, key=emotions_data.get) if emotions_data else "neutral"

    # Pending candidate emotions
    pending_candidates = sorted(list(emotion_model._PENDING_CANDIDATES))

    context = {
        "request": request,
        "entry_id": entry["id"],
        "safe_text": entry.get("safe_text"),
        "dominant_emotion": dominant_emotion.capitalize() if dominant_emotion else None,
        "emotion_summary": emotion_summary_display,
        "entities": entry.get("nlp", {}).get("entities", []),
        "top_matches": top_matches,
        "repetition_pct": repetition_pct,
        "average_similarity_pct": average_similarity_pct,
        "pending_candidates": pending_candidates,
    }

    return templates.TemplateResponse("submit-success.html", context)
