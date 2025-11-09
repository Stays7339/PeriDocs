# app/routes.py
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
import hashlib

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
    if not os.path.exists(file_path):
        return []
    with open(file_path, "r") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []

def save_data(entry, file_path=DATA_FILE):
    """
    Append a new journal entry to the JSON file, ensuring all values are JSON-serializable.
    """
    data = load_data(file_path)
    
    # Sanitize the entry itself
    safe_entry = json_safe(entry)
    
    data.append(safe_entry)
    
    # Final pass on the full dataset just in case
    safe_data = json_safe(data)
    
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(safe_data, f, ensure_ascii=False, indent=2)


def ensure_feedback_file():
    if not os.path.exists(FEEDBACK_FILE):
        with open(FEEDBACK_FILE, "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False, indent=2)

# --- JSON-safety function ---
def json_safe(data):
    if isinstance(data, dict):
        return {k: json_safe(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [json_safe(v) for v in data]
    elif isinstance(data, (np.float32, np.float64, np.int32, np.int64)):
        return float(data)
    else:
        return data

def compute_similarity(vec1, vec2):
    if vec1 is None or vec2 is None:
        return 0.0
    vec1 = np.array(vec1)
    vec2 = np.array(vec2)
    if np.linalg.norm(vec1) == 0 or np.linalg.norm(vec2) == 0:
        return 0.0
    return float(np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2)))

def find_top_matches(entry_vec, all_entries, top_n=20):
    scored_entries = []
    for candidate in all_entries:
        candidate_vec = candidate.get("embedding")
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
    if not tokens:
        return "None"
    words = [t.get("text", "") for t in tokens if t.get("text")]
    excerpt = " ".join(words[:max_words])
    if len(words) > max_words:
        excerpt += "…"
    return excerpt or "None"

def sentiment_percentage(score):
    return max(0, min(100, int((score + 1) / 2 * 100)))

def sentiment_label(score):
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
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/submit")
async def submit_text(request: Request, text: str = Form(...)):
    text = text.strip()
    if not text:
        if request.headers.get("accept") == "application/json":
            return JSONResponse({"status": "error", "message": "No text provided"}, status_code=400)
        return RedirectResponse(url="/#empty", status_code=303)

    features = document_features(text)
    features = json_safe(features)  # --- JSON-safe conversion ---

    sha8 = features.get("sha8") or hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]

    # --- Promote frequently used fields to root ---
    entry = {
        "entry_id": sha8,
        "timestamp": time.time(),
        "encrypted_text": features.get("encrypted_text"),
        "safe_text": features.get("safe_text"),
        "tokens": features.get("tokens", []),
        "entities": features.get("entities", []),
        "embedding": features.get("embedding", []),
        "nlp": {
            "sentiment_score": features.get("sentiment_score", 0.0),
            "sentiment_bucket": features.get("sentiment_bucket", "neutral"),
            "dominant_emotion": features.get("dominant_emotion", "unknown"),
            "emotion_distribution": features.get("emotion_distribution", {}),
            "paraphrase_mirror": features.get("paraphrase_mirror", ""),
            "avg_sentence_length": features.get("avg_sentence_length", 0.0),
            "sentence_count": features.get("sentence_count", 0),
            "repetition_multiplier": features.get("repetition_multiplier", 1.0),
        }
    }

    save_data(entry)

    if request.headers.get("accept") == "application/json":
        return JSONResponse({
            "status": "ok",
            "message": "Journal submitted successfully",
            "entry_id": sha8,
            "redirect_url": f"/submit-success?id={sha8}"
        })

    return RedirectResponse(url=f"/submit-success?id={sha8}", status_code=303)

@app.get("/submit-success", response_class=HTMLResponse)
async def submit_success(request: Request, id: str = None):
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
        last_entry = {"tokens": [], "entities": [], "embedding": [], "nlp": {"sentiment_score": 0.0, "sentiment_bucket": "neutral"}}

    # --- Extract NLP values ---
    nlp_data = last_entry.get("nlp", {})
    tokens = last_entry.get("tokens", [])
    entities = last_entry.get("entities", [])
    embedding = last_entry.get("embedding", [])

    entity_list = [f"{ent['text']} ({ent['label']})" for ent in entities if ent.get("text") and ent.get("label")]
    if not entity_list:
        entity_list = ["None"]

    top_matches = find_top_matches(embedding, [e for e in data if e.get("entry_id") != last_entry.get("entry_id")], top_n=20)

    match_list = []
    similarity_sum = 0.0
    for match in top_matches:
        candidate = match["candidate"]
        sim_pct = int(match["similarity"] * 100)
        similarity_sum += sim_pct
        match_list.append({
            "excerpt": readable_excerpt(candidate.get("tokens", [])),
            "entry_id": candidate.get("entry_id", "N/A"),
            "similarity_pct": sim_pct
        })

    average_similarity_pct = int(similarity_sum / max(1, len(match_list)))

    sentiment_score_val = nlp_data.get("sentiment_score") or 0.0
    sentiment_score = sentiment_percentage(sentiment_score_val)
    sentiment_text_label = sentiment_label(sentiment_score_val)

    repetition_multiplier = nlp_data.get("repetition_multiplier") or 1.0
    repetition_percentage = int((repetition_multiplier - 1.0) * 100)

    dominant_emotion = nlp_data.get("dominant_emotion") or "unknown"
    emotion_dist = nlp_data.get("emotion_distribution") or {}
    emotion_summary = ", ".join([f"{k}: {int(v*100)}%" for k,v in emotion_dist.items() if v > 0.01]) or "No strong emotions detected"

    return templates.TemplateResponse(
        "submit-success.html",
        {
            "request": request,
            "entry_id": last_entry.get("entry_id", "N/A"),
            "safe_text": last_entry.get("safe_text", ""),
            "sentiment_score": sentiment_score,
            "sentiment_label": sentiment_text_label,
            "entity_count": len(entity_list),
            "entities": entity_list,
            "repetition_percentage": repetition_percentage,
            "top_matches": match_list,
            "average_similarity_pct": average_similarity_pct,
            "dominant_emotion": dominant_emotion,
            "emotion_summary": emotion_summary
        }
    )

@app.post("/feedback")
async def submit_feedback(request: Request):
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

@app.get("/terms-of-service", response_class=HTMLResponse)
async def terms_of_service(request: Request):
    return templates.TemplateResponse("terms-of-service.html", {"request": request})

@app.get("/privacy-policy", response_class=HTMLResponse)
async def privacy_page(request: Request):
    return templates.TemplateResponse("privacy.html", {"request": request})

@app.get("/about", response_class=HTMLResponse)
async def about(request: Request):
    return templates.TemplateResponse("about.html", {"request": request})
