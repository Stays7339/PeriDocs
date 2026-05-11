# ==========================================
# app/routes/entry.py
# save-state 2026-04-30T22:04:45 -04:00
# ==========================================
from fastapi import Request, Form, BackgroundTasks, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from glob import glob
import json
import numpy as np
import asyncio
import hashlib
import os
import logging

from app.routes import app
from app.helpers.entry_similarity import cosine_similarity, deterministic_mean, safe_load_embedding
from app.helpers.json_safe import json_safe
from core.nlp.process_entry import process_entry_async
from core.map.deletion import DeletionManager
from core.map.mapping_runtime import ledger, centroid_system , entry_runtime




templates = Jinja2Templates(directory="app/templates")
templates.env.globals["ProductionMode"] = ProductionMode # for making changes easier between Dev mode and Produciton mode

logger = logging.getLogger(__name__)




# ---------------- In-memory progress tracker ----------------
progress_dict: dict[str, float] = {}  # key: entry_id, value: 0.0-1.0

# ---------------- Temp ID → real entry_id mapping ----------------
temp_to_real_entry_id: dict[str, str] = {}  # key: temp_id, value: real entry_id

# ---------------- In-memory delete token store ----------------
delete_tokens_memory: dict[str, str] = {}  # key: real_entry_id, value: delete_token

# ---------------- Active WebSocket connections ----------------
active_ws_connections: dict[str, WebSocket] = {}

async def process_entry_background(entry_text: str, user_ip: str, entry_id: str):
    # ---------------- Wrap progress callback per entry_id ----------------
    def wrapped_progress(fraction: float):
        progress_dict[entry_id] = min(max(fraction, 0.0), 1.0)  # clamp 0–1

    example_variable = await process_entry_async(
        entry_text,
        user_ip=user_ip,
        progress_callback=wrapped_progress
    )

    real_entry_id = example_variable["entry_id"]

    # Store delete_token in memory if it exists
    if example_variable.get("delete_token"):
        delete_tokens_memory[real_entry_id] = example_variable["delete_token"]

    # ---------------- Option A: push crisis immediately ----------------
    if example_variable.get("crisis_flag"):
        ws = active_ws_connections.get(entry_id)
        if ws:
            try:
                await ws.send_json({
                    "type": "crisis",
                    "crisis_flag": True,
                    "real_id": example_variable["entry_id"]
                })
            except WebSocketDisconnect:
                # client already closed, safe to ignore
                pass

    # ---------------- Map temp ID → real entry_id ----------------
    temp_to_real_entry_id[entry_id] = example_variable["entry_id"]

    # ---------------- Store entry (strip embeddings) ----------------
    entry_for_journal = example_variable.copy()
    entry_for_journal.pop("embedding", None)
    entry_for_journal.pop("clause_embeddings", None)
    entry_for_journal.pop("delete_token", None)  # token not persisted
    await entry_runtime.append_entry(entry_for_journal)

    os.makedirs(os.path.join(os.getenv("PERIDOCS_DATA_DIR", "data"), "entries"), exist_ok=True)
    logger.info("Entries in memory: %d", len(entry_runtime.get_all_entries()))

    # ---------------- Update embeddings_index and persist to NPZ ----------------
    if example_variable.get("embedding") is not None:
        await entry_runtime.set_embedding(
            example_variable["entry_id"],
            example_variable["embedding"]
        )

    await entry_runtime._persist() 
    # it is very important to persist entries regularly;
    # otherwise data is lost the moment power is cut.

    # ---------------- Mark progress as complete ----------------
    progress_dict[entry_id] = 1.0


# ---------- Submit entry ----------
@app.post("/submit", response_class=HTMLResponse)
async def submit_entry(
    request: Request,
    entry_text: str | None = Form(None),
    background_tasks: BackgroundTasks = None
):
    # Detect JSON
    if "application/json" in request.headers.get("content-type", ""):
        data = await request.json()
        entry_text = data.get("entry_text", "")

    if not entry_text:
        return JSONResponse({"status": "error", "message": "No entry provided"}, status_code=400)

    client_host = request.client.host if request.client else "127.0.0.1"

    # generate temporary entry_id for progress tracking
    temp_entry_id = f"pending_{np.random.randint(1_000_000, 9_999_999)}"
    progress_dict[temp_entry_id] = 0.0  # ensure initial progress is 0

    # ---------------- Start background processing ----------------
    background_tasks.add_task(process_entry_background, entry_text, client_host, temp_entry_id)

    logger.debug("Submit function triggered for temp_id=%s", temp_entry_id)

    # Immediate response for the user (entry submitted toast)
    return JSONResponse({
        "status": "ok",
        "entry_id": temp_entry_id
    })

# ---------- WebSocket for Progress Updates ----------
@app.websocket("/ws/progress/{entry_id}")
async def entry_progress_ws(websocket: WebSocket, entry_id: str):
    await websocket.accept()
    active_ws_connections[entry_id] = websocket
    try:
        crisis_triggered = False
        while True:
            await asyncio.sleep(0.5)
            real_id = temp_to_real_entry_id.get(entry_id, entry_id)
            progress = progress_dict.get(entry_id, 0.0)

            # Fetch entry if needed (real_id for this specific circumstance)
            entry = entry_runtime.get_entry_by_id(real_id)

            if entry is None:
                crisis_flag = None  # unknown state, not False
            else:
                crisis_flag = entry.get("crisis_flag")

            # --- MINIMAL OPTION A: push crisis immediately ---
            if crisis_flag and not crisis_triggered:
                crisis_triggered = True
                try:
                    await websocket.send_json({
                        "type": "crisis",
                        "crisis_flag": True,
                        "real_id": real_id,
                        "progress": progress
                    })
                except WebSocketDisconnect:
                    pass  # safe to ignore, client already closed
                continue  # skip normal progress message this iteration

            # Compose normal progress message
            message = {
                "progress": progress,
                "real_id": real_id,
                "crisis_flag": crisis_flag
            }

            
            # Send progress message only if crisis not yet triggered
            if not crisis_triggered:
                try:
                    await websocket.send_json(message)
                except WebSocketDisconnect:
                    break  # exit loop safely if client disconnected

            # Optional: add extra sleep if you want to slow down further
            await asyncio.sleep(0.2)  # slow down 200ms between messages

            if progress >= 1.0:
                break
    finally:
        active_ws_connections.pop(entry_id, None)

# ---------- Submit Success ----------
@app.get("/submit-success", response_class=HTMLResponse)
async def submit_success(request: Request, id: str):
    # ---------------- Resolve temp ID → real entry_id ----------------
    id = temp_to_real_entry_id.get(id, id)
    entry = entry_runtime.get_entry_by_id(id)
    if not entry:
        return templates.TemplateResponse(
            "submit-success.html", {"request": request, "error": "Entry not found."}
        )

    # ---------------- Similarity search (runtime-backed) ----------------
    embeddings = await entry_runtime.get_all_embeddings()

    entry_id = entry.get("entry_id") or entry.get("id")
    entry_vec = embeddings.get(entry_id)

    scored_entries = []

    if entry_vec is not None:
        for eid, vec in embeddings.items():
            if eid == entry_id:
                continue

            sim = cosine_similarity(entry_vec, vec)

            match_entry = entry_runtime.get_entry_by_id(eid)

            if match_entry:
                scored_entries.append({
                    "entry": match_entry,
                    "score": sim
                })

    top_matches_formatted = [
        {
            "entry_nickname": e["entry"].get("entry_nickname"),
            "entry_id": json_safe(e["entry"].get("entry_id", e["entry"].get("id"))),
            "excerpt": json_safe(e["entry"].get("safe_text", ""))[:200],
            "similarity_pct": round(max(min(e["score"], 1.0), 0.0) * 100, 1),
        }
        for e in sorted(scored_entries, key=lambda x: x["score"], reverse=True)[:20]
    ]


    delete_token = delete_tokens_memory.pop(entry.get("entry_id", entry.get("id")), None)

    logger.debug("Submit_success function triggered for id=%s", id)

    return templates.TemplateResponse(
        "submit-success.html",
        {
            "request": request,
            "entry_nickname": entry.get("entry_nickname"),
            "entry_id": entry.get("entry_id", entry.get("id")),
            "safe_text": entry.get("safe_text"),
            "top_matches": top_matches_formatted,
            "delete_token": delete_token
        },
    )


# GET -> render delete page
@app.get("/delete", response_class=HTMLResponse)
async def delete_entry_page(request: Request):
    return templates.TemplateResponse(
        "delete.html",
        {"request": request}
    )

# POST -> process delete token
@app.post("/delete", response_class=HTMLResponse)
async def delete_entry_api(request: Request, delete_token: str = Form(...)):
    token_hash = hashlib.sha256(delete_token.encode()).hexdigest()

    

    entry = entry_runtime.get_entry_by_token_hash(token_hash)

    if not entry:
        return templates.TemplateResponse(
            "delete.html",
            {"request": request, "message": "If the entry exists and the token is valid, is has been permanently marked for deletion and will be removed from active records as soon as possible."}
        )

    entry_id = entry.get("entry_id") or entry.get("id")

    try:
        # This is an injection, which helps specify which exact instance to use; 
        # even if it is a singleton, this one works like handing someone an exact physical object,
        # rather than describing the unique details of an exact physical object for them to find on their own.
        # Injection is different from importing, and requires attributes to be passed from function to function,
        # rather than from module to module.
        dm = DeletionManager(   
            ledger=ledger,
            centroids=centroid_system,
            entry_runtime=entry_runtime
        )
        await dm.delete_entry(
            entry_id=entry_id,
            token_hash=token_hash,
            data_dir=os.getenv("PERIDOCS_DATA_DIR", "data")
        )
        # This is a *permutation* not a combination!
        # It's important to remember that the ordering matters everywhere else from here for the deletion pipline downstream.
        # In other words, the deletion token that the user copies must be as follows:
        # [_insert_entry_id_here].[insert_timestamp_here].[insert_the_originally_assigned_ranomized_string_here]
        return templates.TemplateResponse(
            "delete.html",
            {"request": request, "message": "If the entry exists and the token is valid, is has been permanently marked for deletion and will be removed from active records as soon as possible."}
        )
    except Exception as e:
        # Log the full exception server-side
        logger.exception(f"Deletion failed for entry {entry_id}")
        # Return a generic error page to the user
        return templates.TemplateResponse(
            "delete.html",
            {"request": request, "error": "Deletion requests are currently not working. Please contact support."}
        )