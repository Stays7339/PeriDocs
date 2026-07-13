# ==========================================
# app/routes/admin_routing.py
# save-state 2026-07-13T16:13-04:00
# ==========================================
import os
import json
import asyncio
from typing import List, Dict, Any
import hashlib
import re as regex
import uuid
import traceback
import logging

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

logger = logging.getLogger(__name__)

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

    from core.mode_lock import SystemModeLock
    
    if SystemModeLock.resolve_operational_mode() == "DATABASE":
        try:
            from core.database import db_engine
            async with db_engine.pool.connection() as conn:
                rows = await conn.execute("SELECT * FROM content.entries")
                entries = []
                async for row in rows:
                    # Convert row to dictionary/dict-like structure
                    entries.append(dict(row)) 
                ENTRIES_INDEX = entries
        except Exception as e:
            logger.error(f"Failed to load entries from Database: {e}")
            ENTRIES_INDEX = []
    else:
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
    # 1. PRE-PROCESSING (Unified logic)
    if not payload.givens or not payload.outputs:
        raise HTTPException(status_code=400, detail="Missing givens or outputs")

    # Resolve existing concepts for context
    concepts_resp = await get_concepts()
    existing_concepts = concepts_resp.get("concepts", [])

    cleaned_givens = [extract_concept_id(g.strip()) for g in payload.givens]
    cleaned_outputs = []
    output_meta = []  # Tracks metadata for new concepts

    for o in payload.outputs:
        raw_concept = o.get("concept", "").strip()
        extracted_id = extract_concept_id(raw_concept)
        extracted_label = regex.sub(r"\s*\([^)]+\)$", "", raw_concept).strip()

        # Find or create concept logic
        matched_concept = next(
            (c for c in existing_concepts 
             if c["concept_id"].lower() == extracted_id.lower() or c["label"].lower() == extracted_label.lower()), 
            None
        )

        if matched_concept:
            concept_val = matched_concept["concept_id"]
            is_new = False
            file_id_part = None
            label_val = matched_concept["label"]
        else:
            dt = datetime.now(timezone.utc)
            file_id_part = f"cfh_{dt.isoformat(timespec='milliseconds').replace('+00:00', 'Z')}_{uuid.uuid4().hex[:3]}"
            concept_val = f"concept_from_heuristic:{file_id_part}"
            is_new = True
            label_val = extracted_label

        likelihood = float(o.get("likelihood", 0))
        likelihood = max(0.0, min(1.0, likelihood / 100.0 if likelihood > 1 else likelihood))

        cleaned_outputs.append({
            "concept": concept_val,
            "likelihood": likelihood,
            "justification": o.get("justification")
        })
        output_meta.append({"is_new": is_new, "file_id": file_id_part, "label": label_val})

    heuristic = {
        "heuristic_id": f"h_{hashlib.sha256(os.urandom(16)).hexdigest()[:12]}",
        "givens": cleaned_givens,
        "outputs": cleaned_outputs
    }

    # 2. STORAGE FORK
    # --- DATABASE MODE ---
    if SystemModeLock.resolve_operational_mode() == "DATABASE":
        from core.database import db_engine
        DEFAULT_RELEASE_ID = "v0.3.0" 
        
        async with db_engine.pool.connection() as conn:
            async with conn.transaction():
                # A. Register any brand-new concepts first
                for i, meta in enumerate(output_meta):
                    if meta["is_new"]:
                        await conn.execute(
                            "INSERT INTO kb.concepts (concept_id, label) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                            (cleaned_outputs[i]["concept"], meta["label"])
                        )
                
                # B. Insert the heuristic
                await conn.execute(
                    """
                    INSERT INTO kb.heuristics (heuristic_id, givens, outputs, introduced_in_release)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (heuristic["heuristic_id"], heuristic["givens"], json.dumps(heuristic["outputs"]), DEFAULT_RELEASE_ID)
                )
        return {"status": "success", "mode": "database", "heuristic": heuristic}

    # --- FLAT-FILE MODE ---
    else:
        # A. Log the heuristic
        if os.path.exists(HEURISTICS_FILE):
            with open(HEURISTICS_FILE, "r") as f:
                data = json.load(f)
        else:
            data = []
        data.append(heuristic)
        with open(HEURISTICS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        # B. Generate TTLs for new concepts (Original Logic)
        heuristic_description = " | ".join(cleaned_givens)
        for i, o in enumerate(cleaned_outputs):
            meta = output_meta[i]
            if not meta["is_new"]:
                continue
            
            g = Graph()
            if not concept_exists(label=meta["label"], description=heuristic_description):
                create_reasoning_data_from_heuristic(
                    g,
                    heuristic_id=heuristic["heuristic_id"],
                    concept_id=o["concept"],
                    file_id=meta["file_id"],
                    label=meta["label"],
                    description=heuristic_description
                )
                if len(g) > 0:
                    await persist_reasoning_data(meta["file_id"], serialize_graph_to_turtle(g))
        
        return {"status": "success", "mode": "flat-file", "heuristic": heuristic}

@router.get("/concepts")
async def get_concepts():
    try:
        # 1. DATABASE MODE
        if SystemModeLock.resolve_operational_mode() == "DATABASE":
            from core.database import db_engine
            async with db_engine.pool.connection() as conn:
                # 1. Execute the query to get the cursor
                cursor = await conn.execute("SELECT concept_id AS id, label, description FROM kb.concepts")
                # 2. Await the fetchall() to pull rows into a standard list
                rows = await cursor.fetchall()
                # 3. Return the rows directly (they are already dicts!)
                return {"concepts": rows}

        # 2. FLAT-FILE MODE
        else:
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
                    concepts.append({
                        "id": urn_match.group(1),
                        "label": label_match.group(1).strip()
                    })
            return {"concepts": concepts}

    except Exception:
        # This will now correctly capture the full stack trace for 500 errors
        logger.error(f"CRITICAL: /admin/concepts failed: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="Internal server error during concept retrieval")

@router.post("/create-resource")
async def create_resource(payload: CreateResourcePayload):
    """
    Ingests an outlink resource, cleanses the data, and persists it 
    via either Database (Postgres) or Flat-File (JSON) storage.
    """
    
    # 1. PARSING & SANITIZATION (The "Preparation" phase)
    # ---------------------------------------------------
    # Clean concept identifiers
    cleaned_concepts = [c.strip() for c in payload.assigned_concepts if c.strip()]
    if not cleaned_concepts:
        raise HTTPException(status_code=400, detail="Resource must be linked to at least one valid concept.")

    url_clean = payload.url.strip()
    
    # Generate deterministic ID (UUIDv5) to prevent duplicates at the architectural level
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

    # 2. PERSISTENCE BRANCHING (The "Storage" phase)
    # ---------------------------------------------------
    mode = SystemModeLock.resolve_operational_mode()

    # --- CASE A: DATABASE MODE ---
    if mode == "DATABASE":
        from core.database import db_engine
        try:
            async with db_engine.pool.connection() as conn:
                async with conn.transaction():
                    # 1. Persist the main record in 'content.resources'
                    # Uses resource_url as the uniqueness constraint
                    await conn.execute(
                        """
                        INSERT INTO content.resources (resource_id, title, resource_url, resource_type, description)
                        VALUES (%s, %s, %s, %s, %s) 
                        ON CONFLICT (resource_url) DO UPDATE 
                        SET title = %s, resource_type = %s, description = %s;
                        """,
                        (
                            uuid.UUID(new_resource["resource_id"]), 
                            new_resource["title"], 
                            new_resource["url"], 
                            new_resource["resource_type"], 
                            new_resource["description"],
                            new_resource["title"], 
                            new_resource["resource_type"], 
                            new_resource["description"]
                        )
                    )
                    
                    # 2. Retrieve the ID (in case of update, ensuring we have the canonical DB UUID)
                    cursor = await conn.execute(
                        "SELECT resource_id FROM content.resources WHERE resource_url = %s;", 
                        (new_resource["url"],)
                    )
                    row = await cursor.fetchone()
                    r_id = row["resource_id"] if row else None

                    # 3. Bind concepts to 'kb.resource_concept_mappings'
                    for concept in cleaned_concepts:
                        await conn.execute(
                            """
                            INSERT INTO kb.resource_concept_mappings (resource_id, concept_id)
                            VALUES ($1, $2) ON CONFLICT (resource_id, concept_id) DO NOTHING;
                            """,
                            r_id, concept
                        )
            return {"status": "success", "mode": "database", "resource_id": deterministic_id}

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Database persistence failure: {str(e)}")

    # --- CASE B: FLAT-FILE MODE ---
    else:
        try:
            os.makedirs(os.path.dirname(RESOURCES_JSON_FILE), exist_ok=True)
            
            # Load existing records if available
            if os.path.exists(RESOURCES_JSON_FILE):
                loop = asyncio.get_event_loop()
                resources_list = await loop.run_in_executor(None, lambda: json.load(open(RESOURCES_JSON_FILE, "r")))
            else:
                resources_list = []

            # Check for URL collision and perform in-place update or append
            existing_record = next((r for r in resources_list if r["url"] == new_resource["url"]), None)
            
            if existing_record:
                existing_record.update({
                    "title": new_resource["title"],
                    "resource_type": new_resource["resource_type"],
                    "description": new_resource["description"],
                    "assigned_concepts": list(set(existing_record["assigned_concepts"] + cleaned_concepts))
                })
            else:
                resources_list.append(new_resource)

            # Atomic write
            with open(RESOURCES_JSON_FILE, "w", encoding="utf-8") as f:
                json.dump(resources_list, f, indent=2)
                
            return {"status": "success", "mode": "flat-file", "resource_id": deterministic_id}

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Flat-file JSON persistence failure: {str(e)}")