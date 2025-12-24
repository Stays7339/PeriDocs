# ==========================================
# app/routes/__init__.py
# save-state 202512231949
# ==========================================

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import asyncio
from core.map import centroids
from core.nlp.embeddings import _load_model, get_embedding_async
import logging


# ------------------- static file logging filter -------------------
class FilterStatic(logging.Filter):
    def filter(self, record):
        return "/static/" not in record.getMessage()

logging.getLogger("uvicorn.access").addFilter(FilterStatic())
# -------------------------------------------------------------------

app = FastAPI()

@app.on_event("startup")
async def preload_embedding_model():
    print("Preloading SentenceTransformer model (all-roberta-large-v1)...")
    await _load_model()
    print("Model preloaded and ready!")

# ---------------- Embedding Function Wrapper ----------------
async def embedding_async(text: str):
    return await get_embedding_async(text)

# Set async embedding function in centroids
asyncio.create_task(centroids.set_embedding_function(embedding_async))

app.mount("/static", StaticFiles(directory="app/static"), name="static")

from app.routes import info_navigation, journal, feedback, admin  # noqa: F401
