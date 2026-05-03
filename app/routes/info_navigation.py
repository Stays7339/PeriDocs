# ==========================================
# app/routes/info_navigation.py
# routes to /create-entry, /about , /privacy-policy , /terms-of-service and renders the homepage
# save-state 2026-05-03T16:25:05-04:00 (YYYYMMDDhhmm)
# ==========================================

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from app.routes import app  # FastAPI instance from __init__.py

# Jinja2 templates directory
templates = Jinja2Templates(directory="app/templates")


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
    return templates.TemplateResponse("create-entry.html", {"request": request})


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
