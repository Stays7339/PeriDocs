# ==========================================
# app/routes/info_navigation.py
# routes to /create-entry, /about , /privacy-policy , /terms-of-service and renders the homepage
# save-state 2026-07-14T08:51-04:00 (YYYYMMDDhhmm)
# ==========================================

from fastapi import Request, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from app.routes import app, PreventNewEntries  # FastAPI instance from __init__.py
from psycopg import AsyncConnection
from core.database import get_db

# Jinja2 templates directory
templates = Jinja2Templates(directory="app/templates")

@app.get("/healthz")
async def validation_health_check(db: AsyncConnection = Depends(get_db)):
    """
    Diagnostic health route verifying that our async connection pooling 
    can talk natively to our remote PostgreSQL cluster tables.
    """
    try:
        # Check active communication pathways by reading the pinned bundle info
        result = await db.execute('SELECT release_id FROM admin.release_information WHERE is_active = true LIMIT 1;')
        active_bundle = await result.fetchone()
        
        return {
            "status": "healthy",
            "database_connection_active": True,
            "pinned_release": active_bundle["release_id"] if active_bundle else "NO_ACTIVE_RELEASE"
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Pipeline database link failure: {str(e)}"
        )


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """
    Render the homepage.
    """
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/create-entry", response_class=HTMLResponse)
async def about(request: Request):
    """
    Render the Create Entry page.
    """
    return templates.TemplateResponse("create-entry.html", {"request": request, "PreventNewEntries": PreventNewEntries,})


@app.get("/about", response_class=HTMLResponse)
async def about(request: Request):
    """
    Render the About page.
    """
    return templates.TemplateResponse("about.html", {"request": request})


@app.get("/privacy-policy", response_class=HTMLResponse)
async def privacy_policy(request: Request):
    """
    Render the Privacy Policy page.
    """
    return templates.TemplateResponse("privacy.html", {"request": request})


@app.get("/terms-of-service", response_class=HTMLResponse)
async def terms_of_service(request: Request):
    """
    Render the Terms of Service page.
    """
    return templates.TemplateResponse("terms-of-service.html", {"request": request})

@app.get("/ways-to-help", response_class=HTMLResponse)
async def ways_to_help(request: Request):
    """
    Render the Ways To Help page.
    """
    return templates.TemplateResponse("ways-to-help.html", {"request": request})

@app.get("/using-the-site", response_class=HTMLResponse)
async def using_the_site(request: Request):
    """
    Render the Using The Site page.
    """
    return templates.TemplateResponse("using-the-site.html", {"request": request})

@app.get("/suggest-resource", response_class=HTMLResponse)
async def suggest_resource(request: Request):
    """
    Render the Suggest Resource page.
    """
    return templates.TemplateResponse("suggest-resource.html", {"request": request})
