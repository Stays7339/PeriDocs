# ==========================================
# app/routes/__init__.py
# handles initializations on startup
# save-state 202512221555
# ==========================================

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import asyncio
from core.map import centroids
from core.nlp.embeddings import _load_model, get_embedding_async


app = FastAPI()

@app.on_event("startup")
async def preload_embedding_model():
    print("Preloading SentenceTransformer model (all-roberta-large-v1)...")
    await _load_model()
    print("Model preloaded and ready!")


# ---------------- Embedding Function Wrapper ----------------
def embedding_sync(text: str):
    """
    Synchronous wrapper around the async embedding function.
    Ensures compatibility with centroids' synchronous calls.
    """
    return asyncio.get_event_loop().run_until_complete(get_embedding_async(text))


centroids.set_embedding_function(embedding_sync)


app.mount("/static", StaticFiles(directory="app/static"), name="static")

from app.routes import main, journal, feedback, admin  # noqa: F401
