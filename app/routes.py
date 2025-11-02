# app/routes.py

# --- Imports ---
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

import os
import json
import time
import numpy as np
from .nlp import document_features
from datetime import datetime


# --- FastAPI app setup ---
app = FastAPI()

# Mount static files (CSS, JS, images)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Templates directory
templates = Jinja2Templates(directory="app/templates")

# --- Data files ---
BASE_DIR = os.path.dirname(__file__)
DATA_FILE = os.path.join(BASE_DIR, "..", "data", "journals.json")
FEEDBACK_FILE = os.path.join(BASE_DIR, "..", "data", "feedback.json")

# --- Helper functions ---

# Load JSON data from a file, return empty list if missing/corrupt
def load_data(file_path=DATA_FILE):
    if not os.path.exists(file_path):
        return []
    with open(file_path, "r") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []

# Save a new entry to JSON file
def save_data(entry, file_path=DATA_FILE):
    data = load_data(file_path)
    data.append(entry)
    with open(file_path, "w") as f:
        json.dump(data, f, indent=2)

# Load feedback entries specifically
def load_feedback():
    return load_data(FEEDBACK_FILE)

# Save feedback entry
def save_feedback(entry):
    save_data(entry, file_path=FEEDBACK_FILE)

def ensure_feedback_file():
    """Create feedback.json if it doesn't exist and initialize as empty list."""
    if not os.path.exists(FEEDBACK_FILE):
        with open(FEEDBACK_FILE, "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False, indent=2)

# Compute cosine similarity between two vectors
def compute_similarity(vec1, vec2):
    if vec1 is None or vec2 is None:
        return 0.0
    vec1 = np.array(vec1)
    vec2 = np.array(vec2)
    if np.linalg.norm(vec1) == 0 or np.linalg.norm(vec2) == 0:
        return 0.0
    return float(np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2)))

# Find the best matching previous entry
def find_best_match(entry_vec, all_entries, top_n=1):
    best_score = -1
    best_match = None
    for candidate in all_entries:
        candidate_vec = candidate.get("nlp", {}).get("embedding", None)
        if candidate_vec is None:
            continue
        sim = compute_similarity(entry_vec, candidate_vec)
        sentiment_bucket = candidate.get("nlp", {}).get("sentiment", {}).get("bucket", "neutral")
        repetition = candidate.get("nlp", {}).get("repetition_multiplier", 1.0)
        if sentiment_bucket == "positive":
            sim *= 1.1
        elif sentiment_bucket == "negative":
            sim *= 0.9
        sim *= repetition
        if sim > best_score:
            best_score = sim
            best_match = candidate
    return best_match

# Create a readable excerpt from tokens
def readable_excerpt(tokens, max_words=15):
    if not tokens:
        return "None"
    words = [t.get("text", "") for t in tokens if t.get("text")]
    excerpt = " ".join(words[:max_words])
    if len(words) > max_words:
        excerpt += "…"
    return excerpt or "None"

# Convert sentiment score from [-1,1] to [0,100] percentage
def sentiment_percentage(score):
    return max(0, min(100, int((score + 1) / 2 * 100)))

# --- Routes ---

# Homepage
@app.get("/", response_class=HTMLResponse)
async def read_index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# Submit new journal entry
@app.post("/submit", response_class=HTMLResponse)
async def submit_text(request: Request, text: str = Form(...)):
    # Process text with NLP
    features = document_features(text)
    entry = {
        "text": text,
        "nlp": features,
        "entry_id": features["sha8"],
        "timestamp": time.time()
    }
    save_data(entry)
    return RedirectResponse(url=f"/submit-success?id={features['sha8']}", status_code=303)

# Show submit success page with metrics
@app.get("/submit-success", response_class=HTMLResponse)
async def submit_success(request: Request, id: str = None):
    data = load_data()
    last_entry = None

    # Find entry by ID if provided
    if id:
        for e in data:
            if e.get("entry_id") == id:
                last_entry = e
                break

    # Fallback to last entry
    if not last_entry and data:
        last_entry = data[-1]

    # If still none, create empty placeholder
    if not last_entry:
        last_entry = {
            "text": "",
            "nlp": {
                "paraphrase_mirror": "",
                "sentiment": {"score": 0.0, "bucket": "neutral"},
                "entities": [],
                "repetition_multiplier": 1.0,
                "tokens": []
            },
            "entry_id": "N/A"
        }

    # Extract NLP metrics
    nlp_data = last_entry.get("nlp", {})
    entities = nlp_data.get("entities") or []
    entity_list = []
    for ent in entities:
        text = ent.get("text") or None
        label = ent.get("label") or None
        if text and label:
            entity_list.append(f"{text} ({label})")
    if not entity_list:
        entity_list = ["None"]
    entity_count = len(entity_list)

    entry_vec = nlp_data.get("embedding")
    matched_entry = find_best_match(entry_vec, data[:-1]) if entry_vec else None
    matched_tokens = matched_entry.get("nlp", {}).get("tokens") if matched_entry else []
    matched_source_id = matched_entry.get("entry_id", "N/A") if matched_entry else "N/A"
    matched_excerpt = readable_excerpt(matched_tokens)

    sentiment_score = sentiment_percentage(nlp_data.get("sentiment", {}).get("score", 0.0))
    repetition_multiplier = nlp_data.get("repetition_multiplier", 1.0)
    repetition_percentage = int((repetition_multiplier - 1.0) * 100)
    paraphrase = nlp_data.get("paraphrase_mirror", "")

    # Return properly indented
    return templates.TemplateResponse(
        "submit-success.html",
        {
            "request": request,
            "entry_id": last_entry.get("entry_id", "N/A"),
            "paraphrase": paraphrase,
            "sentiment_score": sentiment_score,
            "entity_count": entity_count,
            "entities": entity_list,
            "repetition_percentage": repetition_percentage,
            "matched_excerpt": matched_excerpt,
            "matched_source_id": matched_source_id
        }
    )

#feedback button
@app.post("/feedback")
async def submit_feedback(request: Request):
    """
    Accepts JSON like:
    {
        "feedback_text": "Something went wrong",
        "type": "feedback"  # or "report"
    }
    and appends to feedback.json
    """
    data = await request.json()
    feedback_text = data.get("feedback_text", "").strip()
    feedback_type = data.get("type", "feedback")

    if not feedback_text:
        return JSONResponse({"status": "error", "message": "No text provided"}, status_code=400)

    # Ensure the feedback.json file exists
    ensure_feedback_file()

    # DEBUG: Show where the file is expected
    print("Attempting to write feedback to:", FEEDBACK_FILE)

    # Load current feedback
    try:
        with open(FEEDBACK_FILE, "r", encoding="utf-8") as f:
            feedback_list = json.load(f)
    except json.JSONDecodeError:
        # In case file is empty or malformed, reset as empty list
        feedback_list = []

    # Append new feedback
    feedback_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "type": feedback_type,
        "text": feedback_text
    }
    feedback_list.append(feedback_entry)

    # Write back safely with debug
    try:
        with open(FEEDBACK_FILE, "w", encoding="utf-8") as f:
            json.dump(feedback_list, f, ensure_ascii=False, indent=2)
        print("Feedback written successfully to:", FEEDBACK_FILE)
    except Exception as e:
        print("Failed to write feedback.json:", e)

    return {"status": "ok"}


# --- Privacy Policy weblink ---
@app.get("/privacy-policy", response_class=HTMLResponse)
async def privacy_page(request: Request):
    return templates.TemplateResponse("privacy.html", {"request": request})
