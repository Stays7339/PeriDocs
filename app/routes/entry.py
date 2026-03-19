# ==========================================
# app/routes/entry.py
# save-state 2026-03-19T16:49:15-04:00
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
from app.helpers.file_ops import load_data, append_entry
from app.helpers.entry_similarity import cosine_similarity, deterministic_mean, safe_load_embedding
from app.helpers.json_safe import json_safe
from core.nlp.process_entry import process_entry_async
from core.map.deletion import DeletionManager
from core.map.mapping_runtime import ledger, centroid_system 



templates = Jinja2Templates(directory="app/templates")
entries_FILE = "data/entries/entries.json"
DATA_DIR = os.getenv("PERIDOCS_DATA_DIR", "data")
logger = logging.getLogger("peridocs.entry-routing")

# ---------------- Load embeddings_index via globbing ----------------
embeddings_index = {}
for path_str in sorted(glob("data/entries/entries_mean_embeddings_dump*.npz")):
    path = Path(path_str)
    if path.exists():
        npz_data = np.load(path, allow_pickle=False)
        for k in npz_data.keys():
            embeddings_index[k] = np.array(npz_data[k], dtype=np.float32)

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
    # Map temp ID → real entry_id
    real_entry_id = example_variable["entry_id"]
    temp_to_real_entry_id[entry_id] = real_entry_id

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
    append_entry(entry_for_journal, entries_FILE)

    # ---------------- Update embeddings_index and persist to NPZ ----------------
    if example_variable.get("embedding") is not None:
        eid = example_variable["entry_id"]
        emb = example_variable["embedding"]

        # Update in-memory index
        embeddings_index[eid] = emb.tolist()  # convert to list for JSON-safe storage

        # Persist to .npz
        npz_path = example_variable.get("embedding_file")
        if npz_path:
            Path(npz_path).parent.mkdir(parents=True, exist_ok=True)
            if Path(npz_path).exists():
                loaded = dict(np.load(npz_path, allow_pickle=False))
            else:
                loaded = {}
            loaded[eid] = emb
            np.savez_compressed(npz_path, **loaded)

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

            # Fetch entry if needed
            all_entries = load_data(entries_FILE)
            entry = next((e for e in all_entries if e.get("entry_id") == real_id), {})
            crisis_flag = entry.get("crisis_flag", False)

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

            # Debug log
            # print(f"[DEBUG WS SEND] entry_id={entry_id}, progress={progress}, crisis_flag={crisis_flag}")

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

    all_entries = load_data(entries_FILE)
    entry = next(
        (
            e for e in reversed(all_entries)
            if (e.get("entry_id") == id or e.get("id") == id)
            and e.get("safe_text")
        ),
        None
    )
    if not entry:
        return templates.TemplateResponse(
            "submit-success.html", {"request": request, "error": "Entry not found."}
        )

    # Similarity search
    entry_vec = embeddings_index.get(id)
    if entry_vec is None:
        # fallback to avoid zero vector crash
        entry_vec = np.zeros(1024, dtype=np.float32)
    else:
        entry_vec = np.array(entry_vec, dtype=np.float32)
    scored_entries = []

    for eid, vec in embeddings_index.items():
        if eid == id:
            continue
        sim = cosine_similarity(entry_vec, np.array(vec))
        match_entry = next((e for e in all_entries if e.get("entry_id") == eid or e.get("id") == eid), None)
        if match_entry:
            scored_entries.append({"entry": match_entry, "score": sim})

    top_matches_formatted = [
        {
            "entry_id": json_safe(e["entry"].get("entry_id", e["entry"].get("id"))),
            "excerpt": json_safe(e["entry"].get("safe_text", ""))[:200],
            "similarity_pct": round(max(min(e["score"], 1.0), 0.0) * 100, 1),
        }
        for e in sorted(scored_entries, key=lambda x: x["score"], reverse=True)[:20]
    ]


    delete_token = delete_tokens_memory.pop(entry.get("entry_id", entry.get("id")), None)

    return templates.TemplateResponse(
        "submit-success.html",
        {
            "request": request,
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
    all_entries = load_data(entries_FILE)
    entry = next((e for e in all_entries if e.get("delete_token_hash") == token_hash), None)

    if not entry:
        return templates.TemplateResponse(
            "delete.html",
            {"request": request, "message": "If the entry exists and the token is valid, is has been permanently marked for deletion and will be removed from active records as soon as possible."}
        )

    entry_id = entry.get("entry_id") or entry.get("id")

    try:
        dm = DeletionManager(ledger=ledger, centroids=centroid_system)
        await dm.delete_entry(
            entry_id=entry_id,
            token_hash=token_hash,
            data_dir=DATA_DIR
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