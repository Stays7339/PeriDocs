# ==========================================
# app/routes/admin_routing.py
# save-state 202512291240 (YYYYMMDDhhmm)
# ==========================================

from typing import List, Dict, Any
from core.map import centroids
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi import APIRouter
from core.map import admin_review_helpers as review

# ---------------- Router & templates ----------------
router = APIRouter(prefix="/admin", tags=["admin-review"])
templates = Jinja2Templates(directory="app/templates")

# ---------------- Page route ----------------
@router.get("", response_class=HTMLResponse)
async def admin_review_page(request: Request):
    """
    Serves the admin dashboard page.
    """
    return templates.TemplateResponse(
        "admin-review.html",
        {"request": request},
    )

# ---------------- Helpers ----------------
async def _build_summary(samples: List[str], limit: int = 3) -> str:
    cleaned = [s.strip() for s in samples if s.strip()]
    return " … ".join(cleaned[:limit])

# ---------------- PRECENTROID REVIEW ----------------
@router.get("/precentroids")
async def list_precentroids() -> List[Dict[str, Any]]:
    out = []
    for cid in centroids.CENTROIDS.keys():
        if not cid.startswith("precentroid_"):
            continue
        samples = await centroids.get_journal_entry_samples_for_centroid(cid)
        out.append({
            "id": cid,
            "type": "precentroid",
            "summary": await _build_summary(samples),
            "samples": samples,
            "meta": {
                "count": centroids.CENTROID_COUNTS.get(cid, 0),
                "density": centroids.CENTROID_DENSITIES.get(cid),
            },
        })
    return out

@router.post("/precentroid/{cid}/approve")
async def approve_precentroid(cid: str) -> Dict[str, Any]:
    if cid not in centroids.CENTROIDS:
        raise HTTPException(status_code=404, detail="Precentroid not found")
    new_centroid_id = await centroids.promote_precentroid_to_centroid(cid)
    return {
        "status": "promoted",
        "precentroid_id": cid,
        "new_centroid_id": new_centroid_id,
        "next_step": "confirm_centroid_operational",
    }

@router.post("/precentroid/{cid}/reject")
async def reject_precentroid(cid: str) -> Dict[str, Any]:
    if cid not in centroids.CENTROIDS:
        raise HTTPException(status_code=404, detail="Precentroid not found")
    centroids.CENTROIDS.pop(cid, None)
    centroids.CENTROID_COUNTS.pop(cid, None)
    centroids.CENTROID_VARS.pop(cid, None)
    centroids.CENTROID_DENSITIES.pop(cid, None)
    centroids.CENTROID_METADATA.pop(cid, None)
    centroids.CENTROID_PARENTS.pop(cid, None)
    await centroids.save_centroids()
    return {"status": "rejected", "precentroid_id": cid}

# ---------------- PROMOTED (UNCONFIRMED) CENTROIDS ----------------
@router.get("/pending-centroids")
async def list_unconfirmed_centroids() -> List[Dict[str, Any]]:
    out = []
    for cid in centroids.CENTROIDS.keys():
        if not cid.startswith("centroid_"):
            continue
        meta = centroids.CENTROID_METADATA.get(cid, {})
        if meta.get("status") == "confirmed":
            continue
        samples = await centroids.get_journal_entry_samples_for_centroid(cid)
        out.append({
            "id": cid,
            "type": "centroid_pending",
            "summary": await _build_summary(samples),
            "samples": samples,
            "meta": {
                "count": centroids.CENTROID_COUNTS.get(cid, 0),
                "density": centroids.CENTROID_DENSITIES.get(cid),
                "parent_precentroid": centroids.CENTROID_PARENTS.get(cid),
            },
        })
    return out

@router.post("/centroid/{cid}/confirm")
async def confirm_centroid(cid: str) -> Dict[str, Any]:
    try:
        await centroids.confirm_centroid_operational(cid)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "confirmed", "centroid_id": cid}

# ---------------- SPLIT SUGGESTIONS ----------------
@router.get("/split-suggestions")
async def list_split_suggestions() -> List[Dict[str, Any]]:
    suggestions = await centroids.suggest_split_candidates()
    out = []
    for s in suggestions:
        cid = s["centroid_id"]
        samples = await centroids.get_journal_entry_samples_for_centroid(cid)
        out.append({
            "id": cid,
            "type": "split_suggestion",
            "summary": await _build_summary(samples),
            "samples": samples,
            "meta": s,
        })
    return out

@router.post("/centroid/{cid}/execute-split")
async def execute_split(cid: str) -> Dict[str, Any]:
    if cid not in centroids.CENTROIDS:
        raise HTTPException(status_code=404, detail="Centroid not found")
    samples = await centroids.get_journal_entry_samples_for_centroid(cid)
    if len(samples) < 2:
        raise HTTPException(status_code=400, detail="Not enough samples to split")
    embedding_fn = await centroids.get_embedding_function()
    vectors = [await embedding_fn(t) for t in samples]
    new_ids = await centroids.split_centroid_with_vectors(cid, vectors)
    return {"status": "split_executed", "original_centroid": cid, "new_centroids": new_ids}


@router.get("/admin/review-queue-json")
async def get_review_queue_json():
    await review.initialize_review_queue()
    items = await review.list_review_queue(status="pending")
    # Simplify for cards: id, meta, summary
    out = []
    for r in items:
        samples = r.get("samples", [])
        out.append({
            "id": r["suggestion_id"],
            "summary": samples[0] if samples else "No summary available.",
            "meta": {
                "type": r["suggestion_type"],
                "centroid_id": r["centroid_id"],
                "metrics": r.get("metrics", {}),
                "status": r["status"]
            }
        })
    return out
