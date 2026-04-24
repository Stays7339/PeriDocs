# ==========================================
# app/routes/admin_routing.py
# refactored 2026-04-23T14:26:30-04:00
# ==========================================
import os
import json
import asyncio
from typing import List, Dict, Any
import hashlib

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from core.map.mapping_runtime import centroid_system
from core.map.__init__ import MINIMUM_SIMILARITY_THRESHOLD, BURST_PRECENTROID_STARTING_THRESHOLD

# Initialize router with proper prefix and tags
router = APIRouter(prefix="/admin", tags=["admin-review"])
templates = Jinja2Templates(directory="app/templates")

# -----------------------------
# Pydantic Models
# -----------------------------
class ApprovePrecentroidPayload(BaseModel):
    id: str
    description_from_human_moderator: str
    title_from_human_moderator: str


class RejectPrecentroidPayload(BaseModel):
    id: str


class EntriesSafeTextPayload(BaseModel):
    entry_ids: List[str] = Field(..., description="List of entry IDs to fetch safe_text")

class CreateHeuristicPayload(BaseModel):
    givens: List[str]
    outputs: List[Dict[str, Any]]  # {concept, likelihood, justification?}
# -----------------------------
# Admin HTML Dashboard Route
# -----------------------------
@router.get("/", response_class=HTMLResponse)
async def review_dashboard(request: Request):
    """
    Render the admin review dashboard page with Jinja template.
    """
    return templates.TemplateResponse("admin-review.html", {"request": request})


# -----------------------------
# Review Queue & Precentroid Endpoints
# -----------------------------
@router.get("/review-queue")
async def get_review_queue():
    """
    Retrieve all centroids/precentroids pending human review as JSON.
    """
    return await centroid_system.build_review_queue()


@router.post("/approve-precentroid")
async def approve_precentroid(payload: ApprovePrecentroidPayload):
    """
    Approve a precentroid and convert it into a full centroid.
    """
    new_id = await centroid_system.approve_precentroid(
        payload.id,
        description_from_human_moderator=payload.description_from_human_moderator,
        title_from_human_moderator=payload.title_from_human_moderator
    )
    return {"status": "ok", "new_id": new_id}


@router.post("/reject-precentroid")
async def reject_precentroid(payload: RejectPrecentroidPayload):
    """
    Reject a precentroid.
    """
    await centroid_system.reject_precentroid(
        payload.id,
        threshold=BURST_PRECENTROID_STARTING_THRESHOLD
    )
    return {"status": "ok"}


# -----------------------------
# Entry Safe Text Fetch (async + caching)
# -----------------------------
ENTRIES_FILE = os.path.join("data", "entries", "entries.json")
ENTRIES_INDEX: List[Dict] = []


async def load_entries_index() -> List[Dict]:
    """
    Async load all entries from JSON file into memory.
    Returns list of dicts (entries).
    """
    global ENTRIES_INDEX
    if ENTRIES_INDEX:
        return ENTRIES_INDEX

    try:
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: json.load(open(ENTRIES_FILE, "r")))
        if isinstance(data, list):
            ENTRIES_INDEX = data
        else:
            ENTRIES_INDEX = []
    except Exception:
        ENTRIES_INDEX = []

    return ENTRIES_INDEX


async def find_entry_by_id(entry_id: str) -> Dict:
    """
    Search loaded entries for a given entry_id.
    Returns dict or empty dict if not found.
    """
    entries = await load_entries_index()
    for entry in entries:
        if entry.get("entry_id") == entry_id:
            return entry
    return {}


@router.post("/entries-safe-text")
async def get_entries_safe_text(payload: EntriesSafeTextPayload):
    """
    Given a list of entry_ids, return their safe_text for human moderation.
    """
    results = []
    for eid in payload.entry_ids:
        entry = await find_entry_by_id(eid)
        results.append({
            "entry_id": eid,
            "safe_text": entry.get("safe_text", "")
        })

    return {"entries": results}

HEURISTICS_FILE = os.path.join("data", "heuristics.json")


@router.post("/create-heuristic")
async def create_heuristic(payload: CreateHeuristicPayload):
    if not payload.givens or not payload.outputs:
        raise HTTPException(status_code=400, detail="Missing givens or outputs")

    # normalize likelihoods (accept % or float)
    cleaned_outputs = []
    for o in payload.outputs:
        concept = o.get("concept")
        if not concept:
            raise HTTPException(status_code=400, detail="Output concept missing")

        likelihood = o.get("likelihood", 0)

        try:
            likelihood = float(likelihood)
        except:
            raise HTTPException(status_code=400, detail="Invalid likelihood")

        if likelihood > 1:
            likelihood = likelihood / 100.0

        if likelihood < 0:
            likelihood = 0.0
            
        cleaned_outputs.append({
            "concept": concept,
            "likelihood": float(likelihood),
            "justification": o.get("justification")
        })

    heuristic = {
        "heuristic_id": f"h_{hashlib.sha256(os.urandom(16)).hexdigest()[:12]}",
        "givens": payload.givens,
        "outputs": cleaned_outputs
    }

    # load existing
    if os.path.exists(HEURISTICS_FILE):
        with open(HEURISTICS_FILE, "r") as f:
            data = json.load(f)
    else:
        data = []

    data.append(heuristic)

    with open(HEURISTICS_FILE, "w") as f:
        json.dump(data, f, indent=2)

    return {"status": "ok", "heuristic": heuristic}