# app/routes.py

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

import os, json
from .nlp import analyze_text

# --- FastAPI app ---
app = FastAPI()

# mount static files (background images, etc.)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# templates directory
templates = Jinja2Templates(directory="app/templates")

# --- data file ---
BASE_DIR = os.path.dirname(__file__)
DATA_FILE = os.path.join(BASE_DIR, "..", "data", "journals.json")

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

# --- routes ---
@app.get("/", response_class=HTMLResponse)
async def read_index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/submit", response_class=HTMLResponse)
async def submit_text(request: Request, text: str = Form(...)):
    result = analyze_text(text)
    save_data({"text": text, "nlp": result})
    return RedirectResponse(url="/submit-success", status_code=303)


@app.get("/submit-success", response_class=HTMLResponse)
async def submit_success(request: Request):
    data = load_data()
    last_entry = data[-1] if data else {}
    return templates.TemplateResponse(
        "submit-success.html",
        {
            "request": request,
            "entry_id": len(data),
            "paraphrase": last_entry.get("text", ""),
            "matched_excerpt": last_entry.get("nlp", {}).get("tokens", []),
            "matched_source_id": "N/A"
        }
    )
