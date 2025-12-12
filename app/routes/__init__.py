# app/routes/__init__.py
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import asyncio
from core.nlp.embeddings import _load_model

# FastAPI app instance
app = FastAPI()

# Preload embedding model at startup
@app.on_event("startup")
async def preload_embedding_model():
    print("Preloading SentenceTransformer model (all-roberta-large-v1)...")
    await _load_model()
    print("Model preloaded and ready!")

# Mount static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Import route modules so endpoints are registered
from app.routes import main, journal, feedback  # noqa: F401
