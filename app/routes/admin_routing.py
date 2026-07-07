# ==========================================
# app/routes/admin_routing.py
# save-state 2026-07-06T20:53-04:00
# ==========================================
import os
import json
import asyncio
from typing import List, Dict, Any
import hashlib
import re as regex
import uuid

from datetime import datetime, timezone
from rdflib import Graph
from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from pathlib import Path

from core.mode_lock import SystemModeLock  # Enforces DB vs Flat-File runtime constraint
from core.map.mapping_runtime import centroid_system
from core.map.__init__ import MINIMUM_SIMILARITY_THRESHOLD, BURST_PRECENTROID_STARTING_THRESHOLD
from core.map.perist_reasoning_data import (
    create_reasoning_data_from_heuristic,
    serialize_graph_to_turtle,
    persist_reasoning_data,
    concept_exists
)

DATA_DIR = os.getenv("PERIDOCS_DATA_DIR", "data")
HEURISTICS_FILE = os.path.join("data", "reasoning", "heuristics.json")
os.makedirs(os.path.dirname(HEURISTICS_FILE), exist_ok=True)
RESOURCES_JSON_FILE = os.path.join("data", "reasoning", "resources.json")

# Initialize router with proper prefix and tags
router = APIRouter(
    prefix="/admin",
    tags=["admin-review"]
)

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

class CreateResourcePayload(BaseModel):
    title: str = Field(..., min_length=1)
    url: str = Field(..., min_length=1)
    resource_type: str = Field(..., min_length=1)
    description: str | None = None
    assigned_concepts: List[str] = Field(..., min_length=1)


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

def normalize_concept(s: str) -> str:
    if not s:
        return ""

    s = s.strip().lower()

    # centroid alias → canonical id form
    # handles BOTH "centroid 6" and "centroid6"
    if s.startswith("centroid"):
        s = regex.sub(r"centroid\s*(\d+)", r"centroid_\1", s)
        return s

    # label normalization
    # collapse punctuation + normalize whitespace
    s = regex.sub(r"[^a-z0-9_\s]", "", s)
    s = regex.sub(r"\s+", " ", s).strip()
    return s

def extract_concept_id(value: str) -> str:
    """
    Converts:
    'label (concept_from_heuristic:cfh_2026...)'
    → 'concept_from_heuristic:cfh_2026...'

    If no parentheses, returns original string.
    """
    match = regex.search(r"\(([^)]+)\)$", value)
    return match.group(1) if match else value

@router.post("/create-heuristic")
async def create_heuristic(payload: CreateHeuristicPayload):
    if not payload.givens or not payload.outputs:
        raise HTTPException(status_code=400, detail="Missing givens or outputs")

    cleaned_givens = [extract_concept_id(g.strip()) for g in payload.givens]

    cleaned_outputs = []
    for o in payload.outputs:
        concept = extract_concept_id(o.get("concept", "").strip())

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
        "givens": cleaned_givens,
        "outputs": cleaned_outputs
    }

    # persist heuristic log (unchanged)
    if os.path.exists(HEURISTICS_FILE):
        with open(HEURISTICS_FILE, "r") as f:
            data = json.load(f)
    else:
        data = []

    data.append(heuristic)

    with open(HEURISTICS_FILE, "w") as f:
        json.dump(data, f, indent=2)

    heuristic_description = " | ".join(cleaned_givens)

    # ============================================================
    # NEW BEHAVIOR: ONE OUTPUT → ONE GRAPH → ONE TTL FILE
    # ============================================================
    for o in cleaned_outputs:
        concept_id = o["concept"]

        dt = datetime.now(timezone.utc)
        file_id = f"cfh_{dt.isoformat(timespec='milliseconds').replace('+00:00', 'Z')}_{uuid.uuid4().hex[:3]}"

        # IMPORTANT: each output gets its own isolated graph
        g = Graph()

        already_exists = concept_exists(
            label=concept_id,
            description=heuristic_description
        )

        if not already_exists:
            create_reasoning_data_from_heuristic(
                g,
                heuristic_id=heuristic["heuristic_id"],
                concept_id=concept_id,
                file_id=file_id,
                label=concept_id,
                description=heuristic_description
            )
        else:
            # concept already exists → skip TTL creation entirely
            continue

        # nothing to serialize if we didn't add anything
        if len(g) == 0:
            continue

        turtle = serialize_graph_to_turtle(g)

        await persist_reasoning_data(
            file_id,
            turtle
        )

    return {"status": "ok", "heuristic": heuristic}

@router.get("/concepts")
async def get_concepts():
    """
    Return list of concepts from TTL files for autocomplete.
    Each item includes:
    - id
    - label (human-readable)
    """

    concepts = []
    ttl_dir = Path("data/reasoning")

    if not ttl_dir.exists():
        return {"concepts": []}

    for file in ttl_dir.glob("*.ttl"):
        text = file.read_text(encoding="utf-8")

        urn_match = regex.search(
            r"urn:peridocs:(centroid:centroid_\d+|concept_from_heuristic:[^>\s]+)",
            text
        )

        label_match = regex.search(r'rdfs:label\s+"([^"]+)"', text)
        
        if urn_match and label_match:
            cid = urn_match.group(1)
            label = label_match.group(1).strip()

            concepts.append({
                "id": cid,
                "label": label
            })

    return {"concepts": concepts}


@router.post("/create-resource")
async def create_resource(payload: CreateResourcePayload):
    """
    Ingests an outlink resource and binds it to system concepts.
    Adapts automatically between Postgres and Flat-File JSON modes.
    """
    # Clean and normalize concept strings from the typeahead field
    cleaned_concepts = [extract_concept_id(c.strip()) for c in payload.assigned_concepts]
    cleaned_concepts = [c for c in cleaned_concepts if c]

    if not cleaned_concepts:
        raise HTTPException(status_code=400, detail="Resource must be linked to at least one valid concept.")

    url_clean = payload.url.strip()
    
    # Programmatic Resource_ID generated deterministically via URL hash matching standard UUID rules
    deterministic_id = str(uuid.uuid5(uuid.NAMESPACE_URL, url_clean))

    new_resource = {
        "resource_id": deterministic_id,
        "title": payload.title.strip(),
        "url": url_clean,
        "resource_type": payload.resource_type.strip(),
        "description": payload.description.strip() if payload.description else "",
        "assigned_concepts": cleaned_concepts,
        "created_at": datetime.now(timezone.utc).isoformat()
    }

    # =========================================================================
    # DUAL PERSISTENCE STRATEGY
    # =========================================================================
    
    # CASE A: POSTGRESQL ENGINE MODE
    from core.mode_lock import SystemModeLock
    
    if SystemModeLock.resolve_operational_mode() == "DATABASE":
        from core.database import db_engine
        try:
            async with db_engine.pool.acquire() as conn:
                async with conn.transaction():
                    # Insert Master Resource Record with the alpha-ready schema extensions
                    await conn.execute(
                        """
                        INSERT INTO kb_schema.external_resources (resource_id, title, url, resource_type, description)
                        VALUES ($1, $2, $3, $4, $5) 
                        ON CONFLICT (url) DO UPDATE SET title = $2, resource_type = $4, description = $5;
                        """,
                        uuid.UUID(new_resource["resource_id"]), 
                        new_resource["title"], 
                        new_resource["url"], 
                        new_resource["resource_type"], 
                        new_resource["description"]
                    )
                    
                    r_id = await conn.fetchval("SELECT resource_id FROM kb_schema.external_resources WHERE url = $1;", new_resource["url"])

                    # Bind concepts to relationship mapping table
                    for concept in cleaned_concepts:
                        await conn.execute(
                            """
                            INSERT INTO kb_schema.resource_concept_mappings (resource_id, concept_id)
                            VALUES ($1, $2) ON CONFLICT (resource_id, concept_id) DO NOTHING;
                            """,
                            r_id, concept
                        )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"PostgreSQL persistence failure: {str(e)}")

    # CASE B: FLAT-FILE MODE (JSON/NPZ)
    else:
        try:
            os.makedirs(os.path.dirname(RESOURCES_JSON_FILE), exist_ok=True)
            
            if os.path.exists(RESOURCES_JSON_FILE):
                loop = asyncio.get_event_loop()
                resources_list = await loop.run_in_executor(None, lambda: json.load(open(RESOURCES_JSON_FILE, "r")))
            else:
                resources_list = []

            # Check for existing URL conflict to update record in-place
            existing_record = next((r for r in resources_list if r["url"] == new_resource["url"]), None)
            if existing_record:
                existing_record["title"] = new_resource["title"]
                existing_record["resource_type"] = new_resource["resource_type"]
                existing_record["description"] = new_resource["description"]
                existing_record["assigned_concepts"] = list(set(existing_record["assigned_concepts"] + cleaned_concepts))
            else:
                resources_list.append(new_resource)

            with open(RESOURCES_JSON_FILE, "w", encoding="utf-8") as f:
                json.dump(resources_list, f, indent=2)

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Flat-file JSON persistence failure: {str(e)}")

    return {"status": "ok", "resource_id": new_resource["resource_id"]}