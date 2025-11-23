"""
app/routes/journal.py

Handles journal submission and success pages: "/submit", "/submit-success".
"""

from fastapi import Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime
from typing import Dict
from app.routes import app
from app.helpers.file_ops import load_data, save_data
from app.helpers.top_matches import find_top_matches
from core.nlp import process_entry, sentiment_label, repetition_score
from core.nlp.emotion_analysis import normalize_emotion_profile

# Jinja2 templates directory
templates = Jinja2Templates(directory="app/templates")

# Path to journal data
DATA_FILE = "../data/journals.json"


@app.post("/submit", response_class=HTMLResponse)
async def submit_journal(request: Request, entry_text: str = Form(...)):
    """
    Process a submitted journal entry:
    - Process with NLP pipeline
    - Normalize emotion profile globally
    - Store in journals.json
    - Redirect to success page
    """
    nlp_result = process_entry(entry_text)

    # -------------------------------
    # GLOBAL NORMALIZATION OF EMOTIONS
    # -------------------------------
    if "emotions" in nlp_result:
        nlp_result["emotions"] = normalize_emotion_profile(nlp_result["emotions"])

    entry = {
        "id": nlp_result["sha8_id"],
        "text": entry_text,
        "nlp": nlp_result,
        "timestamp": datetime.utcnow().isoformat()
    }

    save_data(entry, file_path=DATA_FILE)
    return RedirectResponse("/submit-success?id=" + entry["id"], status_code=303)


@app.get("/submit-success", response_class=HTMLResponse)
async def submit_success(request: Request, id: str):
    """
    Display the journal submission success page:
    - Show top similar entries
    - Show repetition, sentiment, emotion metrics
    """
    all_entries = load_data(file_path=DATA_FILE)
    entry = next((e for e in all_entries if e["id"] == id), None)

    if entry is None:
        return templates.TemplateResponse(
            "submit-success.html",
            {"request": request, "error": "Entry not found."}
        )

    # Compute top matches
    top_matches = find_top_matches(
        entry_vec=entry["nlp"]["embedding"],
        all_entries=all_entries,
        top_n=5
    )

    # Compute repetition and sentiment
    repetition_pct = repetition_score(entry["text"])
    sentiment_score = entry["nlp"]["sentiment"]["polarity"]
    sentiment_label_str = sentiment_label(sentiment_score)

    # Compute dominant emotion
    emotions = entry["nlp"].get("emotions", {})
    dominant_emotion = max(emotions, key=emotions.get) if emotions else None

    # Compute average similarity percentage
    average_similarity_pct = (
        sum(m.get("similarity_pct", 0) for m in top_matches) / len(top_matches)
        if top_matches else 0
    )

    # Entities
    entities = entry["nlp"].get("entities", [])

    # Flattened context for template
    context = {
        "request": request,
        "entry_id": entry["id"],
        "safe_text": entry["text"],
        "sentiment_score": sentiment_score,
        "sentiment_label": sentiment_label_str,
        "dominant_emotion": dominant_emotion,
        "emotion_summary": emotions,
        "entities": entities,
        "average_similarity_pct": round(average_similarity_pct, 2),
        "top_matches": top_matches,
        "repetition_pct": repetition_pct
    }

    return templates.TemplateResponse("submit-success.html", context)
