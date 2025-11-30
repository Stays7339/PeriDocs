"""
app/routes/journal.py

PeriDocs Journal Submission and Display Routes
----------------------------------------------

This module defines FastAPI endpoints and helper logic for handling user journal submissions,
processing NLP analyses, storing entries, and managing embeddings. It enforces separation
between content storage and vector embeddings for efficient retrieval and privacy.

Key Features:
-------------
1. **/submit (POST)**:
   - Receives raw journal text from the user.
   - Applies PII redaction upstream (`core.nlp.pii.redact_pii`) with `redact_names=False` during testing.
   - Runs async NLP processing (`process_entry_async`) to extract sentiment, emotion, entities, and embeddings.
   - Normalizes emotion profiles via `normalize_emotion_profile`.
   - Prunes the entry for safe storage in `journals.json` (embeddings removed).
   - Stores normalized embeddings separately in a 6-hour windowed file
     (`journals_embeddings_dumpYYYYMMDD_window.json`).
   - Returns a redirect to `/submit-success`.

2. **/submit-success (GET)**:
   - Displays the submitted journal entry with computed NLP metadata.
   - Shows top-matching entries from embeddings (`get_top_matches`), along with similarity percentages.
   - Provides repetition score, sentiment label, dominant emotion, emotion distribution, and entities.

3. **Embeddings Management**:
   - Each 6-hour window has its own embeddings file to reduce collision and maintain consistency.
   - Embeddings are loaded at startup and updated per submission.
   - Entries in `journals.json` never contain embeddings, maintaining separation of content and vector data.

Security & Privacy:
------------------
- Embeddings and textual content are separated to minimize exposure.
- NLP metadata stored in `journals.json` is safe for display (embeddings removed).
- PII redaction is applied upstream, with name redaction currently disabled for testing.
"""
from fastapi import Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import json
from pathlib import Path
from datetime import datetime
import numpy as np
from glob import glob

from app.routes import app
from app.helpers.file_ops import load_data, append_entry
from app.helpers.journal_helpers import prune_entry, sentiment_label, safe_normalize_embedding
from core.nlp.process_entry import process_entry_async, get_top_matches
from core.nlp.emotion_analysis import normalize_emotion_profile
from core.nlp import repetition_score
from core.nlp.pii import redact_pii  # <- import the PII redactor

templates = Jinja2Templates(directory="app/templates")

JOURNALS_FILE = "data/journals.json"

# ------------------------------
# Determine 6-hour backup window (created on sever spin-up)
# ------------------------------
now = datetime.now()
window = now.hour // 6  # 0: 00-05, 1: 06-11, 2: 12-17, 3: 18-23
BACKUP_TIMESTAMP = now.strftime("%Y%m%d") + f"_{window}"
JOURNALS_EMBED_FILE = f"data/journals_embeddings_dump{BACKUP_TIMESTAMP}.json"



# ------------------------------
# Load all embeddings files with the common prefix
# ------------------------------
embeddings_index = {}
for path_str in sorted(glob("data/journals_embeddings_dump*.json")):
    path = Path(path_str)
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                embeddings_index.update(data)  # merge previous entries
        except Exception as e:
            print(f"Warning: failed to load {path}: {e}")

# ---------- Submit Journal ----------
@app.post("/submit", response_class=HTMLResponse)
async def submit_journal(request: Request, entry_text: str = Form(...)):
    client_host = request.client.host if request.client else "127.0.0.1"

    # REDACT PII
    entry_text_safe = redact_pii(entry_text, redact_names=False)

    # NLP PROCESSING
    nlp_result = await process_entry_async(entry_text_safe, user_ip=client_host)

    # --- Normalize emotions ---
    if "emotions" in nlp_result:
        emotions = nlp_result["emotions"]
        if isinstance(emotions, dict) and "weighted" in emotions:
            emotions["weighted"] = normalize_emotion_profile(emotions["weighted"])
        else:
            nlp_result["emotions"] = normalize_emotion_profile(emotions)

    # --- Fallback if no 'emotions' key ---
    if not nlp_result.get("emotions") and nlp_result.get("weighted_emotion_distribution"):
        nlp_result["emotions"] = nlp_result["weighted_emotion_distribution"]

    # --- Ensure JSON-safe weighted_emotion_distribution and dominant_emotion ---
    if nlp_result.get("weighted_emotion_distribution"):
        # Convert np.float64 → float
        nlp_result["weighted_emotion_distribution"] = {
            k: float(v) for k, v in nlp_result["weighted_emotion_distribution"].items()
        }
        # Compute dominant emotion
        nlp_result["dominant_emotion"] = max(
            nlp_result["weighted_emotion_distribution"],
            key=nlp_result["weighted_emotion_distribution"].get
        )

    # Also make sure 'emotions' is JSON-safe if it exists
    if nlp_result.get("emotions"):
        nlp_result["emotions"] = {
            k: float(v) if isinstance(v, (np.floating, float)) else v
            for k, v in nlp_result["emotions"].items()
        }

    # Preserve entities (ensure JSON-safe)
    if nlp_result.get("entities"):
        nlp_result["entities"] = [str(e) for e in nlp_result["entities"]]

    nlp_result["text"] = entry_text_safe

    # PRUNE ENTRY: embeddings removed
    pruned_entry = prune_entry(nlp_result, keep_embeddings=False)
    pruned_entry["embedding"] = f"stored in {JOURNALS_EMBED_FILE}"

    append_entry(pruned_entry, JOURNALS_FILE)

    # HANDLE EMBEDDINGS SEPARATELY
    embedding_vec = nlp_result.get("embedding")
    norm_vec = safe_normalize_embedding(embedding_vec)
    if norm_vec is not None:
        embeddings_index[nlp_result["sha8"]] = norm_vec
        with open(JOURNALS_EMBED_FILE, "w", encoding="utf-8") as f:
            json.dump(embeddings_index, f, ensure_ascii=False, indent=2)

    return RedirectResponse(f"/submit-success?id={pruned_entry['id']}", status_code=303)

# ---------- Submit Success ----------
@app.get("/submit-success", response_class=HTMLResponse)
async def submit_success(request: Request, id: str):
    all_entries = load_data(JOURNALS_FILE)
    entry = next((e for e in all_entries if isinstance(e, dict) and e.get("id") == id), None)
    if entry is None:
        return templates.TemplateResponse(
            "submit-success.html", {"request": request, "error": "Entry not found."}
        )

    entry_vec = embeddings_index.get(entry["id"])
    top_matches = []
    total_sim = 0.0

    if entry_vec:
        top_match_ids = get_top_matches(entry_vec, embeddings_index, top_n=20)
        for eid, sim in top_match_ids:
            if eid == entry["id"]:
                continue
            match_entry = next((e for e in all_entries if isinstance(e, dict) and e.get("id") == eid), None)
            if match_entry:
                # --- CLIP SIMILARITY TO [0,1] RANGE ---
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
    sentiment_score = entry["nlp"].get("sentiment", 0.0)

    # -------------------------------
    # EMOTION FORMATTING FOR DISPLAY
    # -------------------------------
    # Extract weighted emotions safely for display
    emotions_data = entry["nlp"].get("emotions")
    if isinstance(emotions_data, dict) and "weighted" in emotions_data:
        raw_emotions = emotions_data["weighted"]
    elif emotions_data:
        raw_emotions = emotions_data
    else:
        raw_emotions = entry["nlp"].get("weighted_emotion_distribution", {})

    # Convert to percentages, capitalize keys
    emotion_summary_display = ", ".join(
        f"{k.capitalize()}: {v*100:.1f}%" for k, v in raw_emotions.items()
    )

    # Dominant emotion formatting
    dominant_emotion = max(raw_emotions, key=raw_emotions.get) if raw_emotions else None
    dominant_emotion_display = dominant_emotion.capitalize() if dominant_emotion else None

    context = {
        "request": request,
        "entry_id": entry["id"],
        "safe_text": entry.get("safe_text"),
        "sentiment_label": sentiment_label(sentiment_score.get("polarity", 0.0) if isinstance(sentiment_score, dict) else sentiment_score),
        "dominant_emotion": dominant_emotion_display,
        "emotion_summary": emotion_summary_display,
        "entities": entry["nlp"].get("entities", []),
        "top_matches": top_matches,
        "repetition_pct": repetition_pct,
        "average_similarity_pct": average_similarity_pct
    }
    return templates.TemplateResponse("submit-success.html", context)
