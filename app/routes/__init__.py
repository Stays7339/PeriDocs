# ==========================================
# app/routes/__init__.py
# save-state 202602041326 (YYYYMMDDhhmm)
# ========================================== 

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import asyncio
from core.nlp.embeddings import _load_model, get_embedding_async
import logging
from core.map import ledger, centroids
from core.map.mapping_runtime import initialize_runtime


# ------------------- static file logging filter -------------------
class FilterStatic(logging.Filter):
    def filter(self, record):
        return "/static/" not in record.getMessage()

logging.getLogger("uvicorn.access").addFilter(FilterStatic())
# -------------------------------------------------------------------

app = FastAPI()
print(">>> FASTAPI APP INSTANTIATED FROM app/routes/__init__.py <<<")

# ********* app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None) is important for not leaving the backend publicly exposed *********


@app.on_event("startup")
async def preload_embedding_model():
    print("Preloading SentenceTransformer model (all-roberta-large-v1)...")
    await _load_model()
    print("Model preloaded and ready!")

@app.on_event("startup")
async def load_mapping_runtime():
    print("Initializing mapping runtime...")
    await initialize_runtime(verify=True)
    print("Mapping runtime initialization complete.")


# ---------------- Static Files ----------------
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# ---------------- Import app-bound routes (side effects only) ----------------
from app.routes import info_navigation
from app.routes import journal
from app.routes import feedback

# ---------------- Include router-based routes ----------------
from app.routes import admin_routing
app.include_router(admin_routing.router)

