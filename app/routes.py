# app/routes.py — annotated version with emotion display added
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
import os
import json
import time
import numpy as np
from datetime import datetime
from .nlp import document_features

# --- Load encryption key from .env file ---
load_dotenv()  # ensures AES key is available via environment variable

# --- FastAPI app setup ---
app = FastAPI()
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

# --- Data paths ---
BASE_DIR = os.path.dirname(__file__)
DATA_FILE = os.path.join(BASE_DIR, "..", "data", "journals.json")
FEEDBACK_FILE = os.path.join(BASE_DIR, "..", "data", "feedback.json")

# --- Helper functions ---
def load_data(file_path=DATA_FILE):
    """Load JSON data safely, returning [] if missing or malformed"""
    if not os.path.exists(file_path):
        return []
    with open(file_path, "r") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []

def save_data(entry, file_path=DATA_FILE):
    """Append new journal entry and rewrite file neatly"""
    data = load_data(file_path)
    data.append(entry)
    with open(file_path, "w") as f:
        json.dump(data, f, indent=2)

def ensure_feedback_file():
    """Ensure feedback file exists for storage"""
    if not os.path.exists(FEEDBACK_FILE):
        with open(FEEDBACK_FILE, "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False, indent=2)

def compute_similarity(vec1, vec2):
    """Compute cosine similarity between two embedding vectors"""
    if vec1 is None or vec2 is None:
        return 0.0
    vec1 = np.array(vec1)
    vec2 = np.array(vec2)
    if np.linalg.norm(vec1) == 0 or np.linalg.norm(vec2) == 0:
        return 0.0
    return float(np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2)))

def find_top_matches(entry_vec, all_entries, top_n=20):
    """Return top N similar entries by cosine similarity"""
    scored_entries = []
    for candidate in all_entries:
        candidate_vec = candidate.get("nlp", {}).get("embedding")
        if candidate_vec is None:
            continue
        sim = compute_similarity(entry_vec, candidate_vec)

        # Optional weighting by sentiment and repetition
        sentiment_bucket = candidate.get("nlp", {}).get("sentiment_bucket", "neutral")
        repetition = candidate.get("nlp", {}).get("repetition_multiplier", 1.0)
        if sentiment_bucket == "positive":
            sim *= 1.1
        elif sentiment_bucket == "negative":
            sim *= 0.9
        sim *= repetition
        scored_entries.append({"candidate": candidate, "similarity": sim})

    scored_entries.sort(key=lambda x: x["similarity"], reverse=True)
    return scored_entries[:top_n]

def readable_excerpt(tokens, max_words=15):
    """Generate short readable excerpt for matched snippets"""
    if not tokens:
        return "None"
    words = [t.get("text", "") for t in tokens if t.get("text")]
    excerpt = " ".join(words[:max_words])
    if len(words) > max_words:
        excerpt += "…"
    return excerpt or "None"

def sentiment_percentage(score):
    """Convert -1.0–1.0 sentiment to 0–100 range"""
    return max(0, min(100, int((score + 1) / 2 * 100)))

def sentiment_label(score):
    """Text label from sentiment float"""
    if score >= 0.6:
        return "very positive"
    elif score >= 0.2:
        return "positive"
    elif score > -0.2:
        return "neutral"
    elif score > -0.6:
        return "negative"
    else:
        return "very negative"

# --- Routes ---
@app.get("/", response_class=HTMLResponse)
async def read_index(request: Request):
    """Serve index page"""
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/submit")
async def submit_text(request: Request, text: str = Form(...)):
    """Process user journal submission"""
    text = text.strip()
    if not text:
        if request.headers.get("accept") == "application/json":
            return JSONResponse({"status": "error", "message": "No text provided"}, status_code=400)
        return RedirectResponse(url="/#empty", status_code=303)

    # --- NLP extraction (sentiment, emotion, embeddings, redaction, etc.) ---
    features = document_features(text)

    # --- Construct structured journal entry ---
    entry = {
        "entry_id": features.get("sha8"),
        "timestamp": time.time(),
        "encrypted_text": features.get("encrypted_text"),
        "safe_text": features.get("safe_text"),
        # NLP section stores derived features only
        "nlp": {
            "sentiment_score": features.get("sentiment_score"),
            "sentiment_bucket": features.get("sentiment_bucket"),
            "dominant_emotion": features.get("dominant_emotion"),
            "emotion_distribution": features.get("emotion_distribution"),
            "paraphrase_mirror": features.get("paraphrase_mirror"),
            "avg_sentence_length": features.get("avg_sentence_length"),
            "sentence_count": features.get("sentence_count"),
            "repetition_multiplier": features.get("repetition_multiplier"),
            "embedding": features.get("embedding"),
            "entities": features.get("entities", []),
            "tokens": features.get("tokens", [])
        }
    }

    save_data(entry)

    # --- Response handling ---
    if request.headers.get("accept") == "application/json":
        return JSONResponse({
            "status": "ok",
            "message": "Journal submitted successfully",
            "entry_id": features["sha8"],
            "redirect_url": f"/submit-success?id={features['sha8']}"
        })

    return RedirectResponse(url=f"/submit-success?id={features['sha8']}", status_code=303)

@app.get("/submit-success", response_class=HTMLResponse)
async def submit_success(request: Request, id: str = None):
    """Render success page with analysis + emotion breakdown"""
    data = load_data()
    last_entry = None
    if id:
        for e in data:
            if e.get("entry_id") == id:
                last_entry = e
                break
    if not last_entry and data:
        last_entry = data[-1]
    if not last_entry:
        last_entry = {"nlp": {"sentiment_score": 0.0, "sentiment_bucket": "neutral", "tokens": []}}

    nlp_data = last_entry.get("nlp", {})
    entities = nlp_data.get("entities") or []
    entity_list = [f"{ent['text']} ({ent['label']})" for ent in entities if ent.get("text") and ent.get("label")]
    if not entity_list:
        entity_list = ["None"]

    entry_vec = nlp_data.get("embedding")
    top_matches = find_top_matches(entry_vec, [e for e in data if e.get("entry_id") != last_entry.get("entry_id")], top_n=20)

    match_list = []
    similarity_sum = 0.0
    for match in top_matches:
        candidate = match["candidate"]
        sim_pct = int(match["similarity"] * 100)
        similarity_sum += sim_pct
        match_list.append({
            "excerpt": readable_excerpt(candidate.get("nlp", {}).get("tokens", [])),
            "entry_id": candidate.get("entry_id", "N/A"),
            "similarity_pct": sim_pct
        })
    average_similarity_pct = int(similarity_sum / max(1, len(match_list)))

    sentiment_score = sentiment_percentage(nlp_data.get("sentiment_score", 0.0))
    sentiment_text_label = sentiment_label(nlp_data.get("sentiment_score", 0.0))
    repetition_multiplier = nlp_data.get("repetition_multiplier", 1.0)
    repetition_percentage = int((repetition_multiplier - 1.0) * 100)

    # --- New: emotion summarization for template display ---
    dominant_emotion = nlp_data.get("dominant_emotion", "unknown")
    emotion_dist = nlp_data.get("emotion_distribution", {})
    emotion_summary = ", ".join(
        [f"{k}: {int(v * 100)}%" for k, v in emotion_dist.items() if v > 0.01]
    ) or "No strong emotions detected"

    # --- Render the success template ---
    return templates.TemplateResponse(
        "submit-success.html",
        {
            "request": request,
            "entry_id": last_entry.get("entry_id", "N/A"),
            "safe_text": nlp_data.get("safe_text", ""),
            "sentiment_score": sentiment_score,
            "sentiment_label": sentiment_text_label,
            "entity_count": len(entity_list),
            "entities": entity_list,
            "repetition_percentage": repetition_percentage,
            "top_matches": match_list,
            "average_similarity_pct": average_similarity_pct,
            "dominant_emotion": dominant_emotion,
            "emotion_summary": emotion_summary  # added for template visibility
        }
    )

@app.post("/feedback")
async def submit_feedback(request: Request):
    """Store feedback text from modal"""
    data = await request.json()
    feedback_text = data.get("feedback_text", "").strip()
    feedback_type = data.get("type", "feedback")
    ip_hash = data.get("ip_hash", "unknown")

    if not feedback_text:
        return JSONResponse({"status": "error", "message": "No text provided"}, status_code=400)

    ensure_feedback_file()
    try:
        with open(FEEDBACK_FILE, "r", encoding="utf-8") as f:
            feedback_list = json.load(f)
    except json.JSONDecodeError:
        feedback_list = []

    feedback_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "type": feedback_type,
        "text": feedback_text,
        "ip_hash": ip_hash
    }
    feedback_list.append(feedback_entry)

    try:
        with open(FEEDBACK_FILE, "w", encoding="utf-8") as f:
            json.dump(feedback_list, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("Failed to write feedback.json:", e)
        return JSONResponse({"status": "error", "message": "Server error"}, status_code=500)

    return {"status": "ok"}

# --- Static pages (unchanged) ---
@app.get("/terms-of-service", response_class=HTMLResponse)
async def terms_of_service(request: Request):
    return templates.TemplateResponse("terms-of-service.html", {"request": request})

@app.get("/privacy-policy", response_class=HTMLResponse)
async def privacy_page(request: Request):
    return templates.TemplateResponse("privacy.html", {"request": request})

@app.get("/about", response_class=HTMLResponse)
async def about(request: Request):
    return templates.TemplateResponse("about.html", {"request": request})
