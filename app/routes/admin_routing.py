# ==========================================
# app/routes/admin_routing.py
# save-state 202601012209
# ==========================================
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from typing import List, Dict, Any
from core.map import centroids
from core.map import admin_review_helpers as review

router = APIRouter(prefix="/admin", tags=["admin-review"])
templates = Jinja2Templates(directory="app/templates")

# ---------------- Page ----------------
@router.get("", response_class=HTMLResponse)
async def admin_review_page(request: Request):
    return templates.TemplateResponse("admin-review.html", {"request": request})

# ---------------- Queue JSON ----------------
@router.get("/review-queue-json")
async def get_review_queue_json():
    # Ensure queue is initialized
    await review.initialize_review_queue()
    items = await review.list_review_queue(status="pending")

    out = []
    for r in items:
        # Determine card type
        if r["suggestion_type"] == "new_centroid":
            card_type = "precentroid"
        elif r["suggestion_type"] == "split_centroid":
            card_type = "split_suggestion"
        else:
            card_type = "unknown"

        # Construct summary from first sample if available
        samples = r.get("samples", [])
        summary = samples[0] if samples else r.get("human_note") or "No summary available."

        # Build meta dictionary
        meta = {
            "centroid_id": r["centroid_id"],
            "metrics": r.get("metrics", {}),
            "status": r["status"],
            "human_labels": r.get("human_labels", []),
            "created_at": r.get("created_at"),
        }

        out.append({
            "id": r["suggestion_id"],
            "type": card_type,
            "summary": summary,
            "meta": meta
        })

    return out
