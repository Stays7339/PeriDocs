# ==========================================
# app/routes/journal.py
# save-state 202512241542
# ==========================================
from fastapi import Request, Form, BackgroundTasks, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from glob import glob
import json
import numpy as np
import asyncio

from app.routes import app
from app.helpers.file_ops import load_data, append_entry
from app.helpers.entry_similarity import compute_similarity_to_other_entries
from app.helpers.json_safe import json_safe
from core.nlp.process_entry import process_entry_async

templates = Jinja2Templates(directory="app/templates")
JOURNALS_FILE = "data/journals.json"

# ---------------- Load embeddings_index via globbing ----------------
embeddings_index = {}
for path_str in sorted(glob("data/journals_embeddings_dump*.json")):
    path = Path(path_str)
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            embeddings_index.update(json.load(f))

# ---------------- In-memory progress tracker ----------------
progress_dict: dict[str, float] = {}  # key: journal_id, value: 0.0-1.0

# ---------------- Temp ID → real journal_id mapping ----------------
temp_to_real_journal_id: dict[str, str] = {}  # key: temp_id, value: real journal_id

# ---------------- Active WebSocket connections ----------------
active_ws_connections: dict[str, WebSocket] = {}

async def process_entry_background(entry_text: str, user_ip: str, journal_id: str):
    # ---------------- Wrap progress callback per journal_id ----------------
    def wrapped_progress(fraction: float):
        progress_dict[journal_id] = min(max(fraction, 0.0), 1.0)  # clamp 0–1

    example_variable = await process_entry_async(
        entry_text,
        user_ip=user_ip,
        progress_callback=wrapped_progress
    )

    # ---------------- Option A: push crisis immediately ----------------
    if example_variable.get("crisis_flag"):
        ws = active_ws_connections.get(journal_id)
        if ws:
            try:
                await ws.send_json({
                    "type": "crisis",
                    "crisis_flag": True,
                    "real_id": example_variable["journal_id"]
                })
            except WebSocketDisconnect:
                # client already closed, safe to ignore
                pass

    # ---------------- Map temp ID → real journal_id ----------------
    temp_to_real_journal_id[journal_id] = example_variable["journal_id"]

    # ---------------- Store journal entry (strip embeddings) ----------------
    entry_for_journal = example_variable.copy()
    entry_for_journal.pop("embedding", None)
    entry_for_journal.pop("clause_embeddings", None)
    append_entry(entry_for_journal, JOURNALS_FILE)

    # ---------------- Update embeddings_index ----------------
    if example_variable.get("embedding"):
        embeddings_index[example_variable["journal_id"]] = example_variable["embedding"]
        embed_path = example_variable.get("embedding_file")
        if embed_path:
            Path(embed_path).parent.mkdir(parents=True, exist_ok=True)
            with open(embed_path, "w", encoding="utf-8") as f:
                json.dump(embeddings_index, f, ensure_ascii=False, indent=2)

    # ---------------- Mark progress as complete ----------------
    progress_dict[journal_id] = 1.0

# ---------- Submit Journal ----------
@app.post("/submit", response_class=HTMLResponse)
async def submit_journal(
    request: Request,
    entry_text: str | None = Form(None),
    background_tasks: BackgroundTasks = None
):
    # Detect JSON
    if request.headers.get("content-type") == "application/json":
        data = await request.json()
        entry_text = data.get("entry_text", "")

    if not entry_text:
        return JSONResponse({"status": "error", "message": "No journal entry provided"}, status_code=400)

    client_host = request.client.host if request.client else "127.0.0.1"

    # generate temporary journal_id for progress tracking
    temp_journal_id = f"pending_{np.random.randint(1_000_000, 9_999_999)}"
    progress_dict[temp_journal_id] = 0.0  # ensure initial progress is 0

    # ---------------- Start background processing ----------------
    background_tasks.add_task(process_entry_background, entry_text, client_host, temp_journal_id)

    # Immediate response for the user (journal submitted toast)
    return JSONResponse({
        "status": "ok",
        "entry_id": temp_journal_id
    })

# ---------- WebSocket for Progress Updates ----------
@app.websocket("/ws/progress/{journal_id}")
async def journal_progress_ws(websocket: WebSocket, journal_id: str):
    await websocket.accept()
    active_ws_connections[journal_id] = websocket
    try:
        crisis_triggered = False
        while True:
            await asyncio.sleep(0.5)
            real_id = temp_to_real_journal_id.get(journal_id, journal_id)
            progress = progress_dict.get(journal_id, 0.0)

            # Fetch entry if needed
            all_entries = load_data(JOURNALS_FILE)
            entry = next((e for e in all_entries if e.get("journal_id") == real_id), {})
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
            # print(f"[DEBUG WS SEND] journal_id={journal_id}, progress={progress}, crisis_flag={crisis_flag}")

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
        active_ws_connections.pop(journal_id, None)

# ---------- Submit Success ----------
@app.get("/submit-success", response_class=HTMLResponse)
async def submit_success(request: Request, id: str):
    # ---------------- Resolve temp ID → real journal_id ----------------
    id = temp_to_real_journal_id.get(id, id)

    all_entries = load_data(JOURNALS_FILE)
    entry = next((e for e in all_entries if e.get("journal_id") == id or e.get("id") == id), None)
    if not entry:
        return templates.TemplateResponse(
            "submit-success.html", {"request": request, "error": "Entry not found."}
        )

    # Similarity search
    entry_vec = np.array(embeddings_index.get(id, np.zeros(1024)))
    scored_entries = []

    for eid, vec in embeddings_index.items():
        if eid == id:
            continue
        sim = compute_similarity_to_other_entries(entry_vec, np.array(vec))
        match_entry = next((e for e in all_entries if e.get("journal_id") == eid or e.get("id") == eid), None)
        if match_entry:
            scored_entries.append({"entry": match_entry, "score": sim})

    top_matches_formatted = [
        {
            "entry_id": json_safe(e["entry"].get("journal_id", e["entry"].get("id"))),
            "excerpt": json_safe(e["entry"].get("safe_text", ""))[:200],
            "similarity_pct": round(max(min(e["score"], 1.0), 0.0) * 100, 1),
        }
        for e in sorted(scored_entries, key=lambda x: x["score"], reverse=True)[:20]
    ]

    return templates.TemplateResponse(
        "submit-success.html",
        {
            "request": request,
            "entry_id": entry.get("journal_id", entry.get("id")),
            "safe_text": entry.get("safe_text"),
            "top_matches": top_matches_formatted,
        },
    )
