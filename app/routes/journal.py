# ==========================================
# app/routes/journal.py
# save-state 202512231945
# ==========================================
from fastapi import Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from glob import glob
import json
import numpy as np

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

# ---------- Submit Journal ----------
@app.post("/submit", response_class=HTMLResponse)
async def submit_journal(
    request: Request,
    entry_text: str | None = Form(None)
):
    # Detect JSON
    if request.headers.get("content-type") == "application/json":
        data = await request.json()
        entry_text = data.get("entry_text", "")

    if not entry_text:
        return JSONResponse({"status": "error", "message": "No journal entry provided"}, status_code=400)

    client_host = request.client.host if request.client else "127.0.0.1"

    # ---------------- Fully delegated to process_entry ----------------
    example_variable = await process_entry_async(entry_text, user_ip=client_host)

    # ---------------- Store journal entry (strip embeddings) ----------------
    entry_for_journal = example_variable.copy()
    entry_for_journal.pop("embedding", None)
    entry_for_journal.pop("clause_embeddings", None)
    append_entry(entry_for_journal, JOURNALS_FILE)

    # ---------------- Update embeddings_index in journal.py ----------------
    if example_variable.get("embedding"):
        embeddings_index[example_variable["journal_id"]] = example_variable["embedding"]
        # persist immediately
        embed_path = example_variable.get("embedding_file")
        if embed_path:
            Path(embed_path).parent.mkdir(parents=True, exist_ok=True)
            with open(embed_path, "w", encoding="utf-8") as f:
                json.dump(embeddings_index, f, ensure_ascii=False, indent=2)

    # Return JSON if requested
    if request.headers.get("accept") == "application/json" or request.headers.get("content-type") == "application/json":
        return JSONResponse({
            "status": "ok",
            "entry_id": example_variable["journal_id"],
        })
    else:
        return RedirectResponse(f"/submit-success?id={example_variable['journal_id']}", status_code=303)


# ---------- Submit Success ----------
@app.get("/submit-success", response_class=HTMLResponse)
async def submit_success(request: Request, id: str):
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
