# app/routes.py

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

import os
import json
import time
import numpy as np
from .nlp import document_features

# --- FastAPI app ---
app = FastAPI()

# mount static files (background images, css)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# templates directory
templates = Jinja2Templates(directory="app/templates")

# --- data file ---
BASE_DIR = os.path.dirname(__file__)
DATA_FILE = os.path.join(BASE_DIR, "..", "data", "journals.json")

# --- helpers ---
def load_data():
    if not os.path.exists(DATA_FILE):
        return []
    with open(DATA_FILE, "r") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []

def save_data(entry):
    data = load_data()
    data.append(entry)
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

def compute_similarity(vec1, vec2):
    if vec1 is None or vec2 is None:
        return 0.0
    vec1 = np.array(vec1)
    vec2 = np.array(vec2)
    if np.linalg.norm(vec1) == 0 or np.linalg.norm(vec2) == 0:
        return 0.0
    return float(np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2)))

def find_best_match(entry_vec, all_entries, top_n=1):
    best_score = -1
    best_match = None
    for candidate in all_entries:
        candidate_vec = candidate.get("nlp", {}).get("embedding", None)
        if candidate_vec is None:
            continue
        sim = compute_similarity(entry_vec, candidate_vec)
        # Apply emotional weighting
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

# --- routes ---
@app.get("/", response_class=HTMLResponse)
async def read_index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/submit", response_class=HTMLResponse)
async def submit_text(request: Request, text: str = Form(...)):
    # --- Run NLP processing ---
    features = document_features(text)

    # --- Prepare entry for storage ---
    entry = {
        "text": text,
        "nlp": features,
        "entry_id": features["sha8"],
        "timestamp": time.time()
    }

    # --- Save locally ---
    save_data(entry)

    # --- Redirect to submit-success page ---
    return RedirectResponse(url=f"/submit-success?id={features['sha8']}", status_code=303)


@app.get("/submit-success", response_class=HTMLResponse)
async def submit_success(request: Request, id: str = None):
    data = load_data()
    last_entry = None

    if id:
        # Try to find the entry with matching SHA8
        for e in data:
            if e.get("entry_id") == id:
                last_entry = e
                break
    if not last_entry and data:
        # fallback to last entry
        last_entry = data[-1]

    if not last_entry:
        # no data
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

    nlp_data = last_entry["nlp"]
    entities = nlp_data.get("entities") or []
    entity_count = len(entities)

    return templates.TemplateResponse(
        "submit-success.html",
        {
            "request": request,
            "entry_id": last_entry.get("entry_id"),
            "paraphrase": nlp_data.get("paraphrase_mirror", ""),
            "sentiment_score": nlp_data.get("sentiment", {}).get("score", 0.0),
            "entity_count": entity_count,
            "entities": [f"{ent['text']} ({ent['label']})" for ent in entities],
            "repetition_multiplier": nlp_data.get("repetition_multiplier", 1.0),
            "matched_excerpt": nlp_data.get("tokens", []),  # placeholder
            "matched_source_id": "N/A"
        }
    )



    last_entry = data[-1]
    entry_vec = last_entry.get("nlp", {}).get("embedding", None)

    # Find best local match for editorial excerpt (cosine similarity + emotional weighting)
    matched_entry = find_best_match(entry_vec, data[:-1]) if entry_vec is not None else None

    matched_excerpt = matched_entry.get("nlp", {}).get("tokens", []) if matched_entry else []
    matched_source_id = matched_entry.get("sha8", "N/A") if matched_entry else "N/A"

    return templates.TemplateResponse(
        "submit-success.html",
        {
            "request": request,
            "entry_id": last_entry.get("sha8", "N/A"),
            "paraphrase": last_entry.get("nlp", {}).get("paraphrase_mirror", ""),
            "matched_excerpt": matched_excerpt,
            "matched_source_id": matched_source_id
        }
    )
