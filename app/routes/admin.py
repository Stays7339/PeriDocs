# ==========================================
# app/routes/admin.py
# save-state updated 202512161750
# ==========================================

from fastapi import Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from urllib.parse import urlencode
from app.routes import app  # FastAPI instance
from core.map import review_helpers

templates = Jinja2Templates(directory="app/templates")


# ---------------- GET: Admin Review Dashboard ----------------
@app.get("/admin-review", response_class=HTMLResponse)
async def admin_review_dashboard(
    request: Request, 
    status: str = None, 
    flash: str = None
):
    """
    Render the centroid review queue dashboard.
    Optional query param `status` filters by suggestion status.
    Flash message shows errors from updates.
    """
    suggestions = review_helpers.list_review_queue(status=status)

    # Attach sample entries for UI
    for s in suggestions:
        s["samples"] = review_helpers.get_centroid_samples(s["centroid_id"])

    return templates.TemplateResponse(
        "admin-review.html",
        {
            "request": request,
            "suggestions": suggestions,
            "flash": flash
        },
    )


# ---------------- POST: Update Status ----------------
@app.post("/admin-review/update-status", response_class=RedirectResponse)
async def admin_review_update_status(
    suggestion_id: str = Form(...),
    status: str = Form(...),
    human_note: str = Form(None),
):
    """
    Update the status and optional human note of a suggestion.
    Shows flash if suggestion_id not found.
    """
    flash = None
    try:
        review_helpers.update_review_status(
            suggestion_id,
            status=status,
            note=human_note if human_note else None,
        )
    except KeyError:
        flash = f"⚠️ Suggestion {suggestion_id} no longer exists."

    redirect_url = "/admin-review"
    if flash:
        redirect_url += "?" + urlencode({"flash": flash})

    return RedirectResponse(redirect_url, status_code=303)


# ---------------- POST: Update Labels ----------------
@app.post("/admin-review/update-labels", response_class=RedirectResponse)
async def admin_review_update_labels(
    suggestion_id: str = Form(...),
    labels: str = Form(...),  # comma-separated
):
    """
    Update human labels for a suggestion.
    Shows flash if suggestion_id not found.
    """
    label_list = [l.strip() for l in labels.split(",") if l.strip()]
    flash = None
    try:
        review_helpers.update_review_labels(
            suggestion_id,
            labels=label_list,
        )
    except KeyError:
        flash = f"⚠️ Suggestion {suggestion_id} no longer exists."

    redirect_url = "/admin-review"
    if flash:
        redirect_url += "?" + urlencode({"flash": flash})

    return RedirectResponse(redirect_url, status_code=303)
