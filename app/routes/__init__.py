"""
app/routes/__init__.py

Initializes FastAPI app and attaches all route modules.
"""
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

# Initialize main FastAPI application
app = FastAPI()

# Mount static files (JS, CSS, images)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Import route modules after app is created
from app.routes import main, journal, feedback  # noqa: F401

