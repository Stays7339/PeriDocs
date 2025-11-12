# app/routes/lexicon_admin.py
"""
Hidden admin route for lexicon moderation.
Requires ADMIN_TOKEN in .env (string). Not linked from navigation.
"""

import os
from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import RedirectResponse
from pathlib import Path
import json
from starlette.templating import Jinja2Templates

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
SUGGESTIONS_PATH = DATA_DIR / "lexicon_suggestions.json"
DYNAMIC_PATH = DATA_DIR / "dynamic_lexicons.json"

templates = Jinja2Templates(directory=str(ROOT / "app" / "templates"))

router = APIRouter()

def check_token(request: Request):
    token = request.cookies.get("admin_token") or request.query_params.get("token")
    if not token or token != os.getenv("ADMIN_TOKEN"):
        raise HTTPException(status_code=401, detail="Unauthorized")

@router.get("/lexicon-admin")
def lexicon_admin(request: Request, _ = Depends(check_token)):
    suggestions = []
    if SUGGESTIONS_PATH.exists():
        with open(SUGGESTIONS_PATH, "r", encoding="utf-8") as fh:
            suggestions = json.load(fh)
    # load dynamic
    dynamic = {}
    if DYNAMIC_PATH.exists():
        with open(DYNAMIC_PATH, "r", encoding="utf-8") as fh:
            dynamic = json.load(fh)
    return templates.TemplateResponse("lexicon_admin.html", {"request": request, "suggestions": suggestions, "dynamic": dynamic})

@router.post("/lexicon-admin/apply")
def lexicon_admin_apply(request: Request, token_to_add: str = Form(...), category: str = Form(...), _ = Depends(check_token)):
    # load dynamic
    dynamic = {}
    if DYNAMIC_PATH.exists():
        with open(DYNAMIC_PATH, "r", encoding="utf-8") as fh:
            dynamic = json.load(fh)
    dynamic.setdefault(category, [])
    if token_to_add.lower() not in [x.lower() for x in dynamic[category]]:
        dynamic[category].append(token_to_add)
    with open(DYNAMIC_PATH, "w", encoding="utf-8") as fh:
        json.dump(dynamic, fh, indent=2, ensure_ascii=False)
    return RedirectResponse(url="/lexicon-admin", status_code=303)
