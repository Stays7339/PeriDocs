# ==========================================
# app/routes/journal.py
# save-state updated 202512161345
# ==========================================
from fastapi import Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from datetime import datetime
from glob import glob
import json
import numpy as np
import aiofiles

from app.routes import app
from app.helpers.file_ops import load_data, append_entry
from app.helpers.entry_similarity import compute_similarity_to_other_entries
from app.helpers.json_safe import json_safe
from core.nlp.process_entry import process_entry_async
from core.nlp.embeddings import get_embedding_async
from core.nlp.pii import redact_pii

templates = Jinja2Templates(directory="app/templates")
JOURNALS_FILE = "data/journals.json"

now = datetime.now()
window = now.hour // 6
BACKUP_TIMESTAMP = now.strftime("%Y%m%d") + f"_{window}"
JOURNALS_EMBED_FILE = f"data/journals_embeddings_dump{BACKUP_TIMESTAMP}.json"

embeddings_index = {}
for path_str in sorted(glob("data/journals_embeddings_dump*.json")):
    path = Path(path_str)
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            embeddings_index.update(json.load(f))

# ---------- Submit Journal ----------
@app.post("/submit", response_class=HTMLResponse)
async def submit_journal(request: Request, entry_text: str = Form(...)):
    client_host = request.client.host if request.client else "127.0.0.1"
    safe_text = redact_pii(entry_text, redact_names=False)
    nlp_result = await process_entry_async(safe_text, user_ip=client_host)

    sha8 = nlp_result["sha8"]
    pruned_entry = {
        "id": sha8,
        "safe_text": safe_text,
        "timestamp": datetime.utcnow().isoformat(),
        "nlp": {
            "embedding": f"stored in {JOURNALS_EMBED_FILE}",
            "emotions": nlp_result.get("emotions", {}),
            "crisis_flag": nlp_result.get("crisis_flag", False),
            "summary": None
        }
    }
    append_entry(pruned_entry, JOURNALS_FILE)

    embedding_vec = np.array(nlp_result["embedding"])
    embeddings_index[sha8] = embedding_vec.tolist()

    async with aiofiles.open(JOURNALS_EMBED_FILE, "w", encoding="utf-8") as f:
        await f.write(json.dumps(embeddings_index, ensure_ascii=False, indent=2))


    return RedirectResponse(f"/submit-success?id={sha8}", status_code=303)

# ---------- Submit Success ----------
@app.get("/submit-success", response_class=HTMLResponse)
async def submit_success(request: Request, id: str):
    all_entries = load_data(JOURNALS_FILE)
    entry = next((e for e in all_entries if e.get("id") == id), None)
    if not entry:
        return templates.TemplateResponse(
            "submit-success.html", {"request": request, "error": "Entry not found."}
        )

    entry_vec = np.array(embeddings_index[id])
    scored_entries = []

    for eid, vec in embeddings_index.items():
        if eid == id:
            continue
        sim = compute_similarity_to_other_entries(entry_vec, np.array(vec))
        match_entry = next((e for e in all_entries if e["id"] == eid), None)
        if match_entry:
            scored_entries.append({"entry": match_entry, "score": sim})

    top_matches_formatted = [
        {
            "entry_id": json_safe(e["entry"]["id"]),
            "excerpt": json_safe(e["entry"].get("safe_text", ""))[:200],
            "similarity_pct": round(max(min(e["score"], 1.0), 0.0) * 100, 1),
        }
        for e in sorted(scored_entries, key=lambda x: x["score"], reverse=True)[:20]
    ]

    return templates.TemplateResponse(
        "submit-success.html",
        {
            "request": request,
            "entry_id": id,
            "safe_text": entry.get("safe_text"),
            "top_matches": top_matches_formatted,
        },
    )

