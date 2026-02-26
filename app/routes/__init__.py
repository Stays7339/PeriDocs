# ==========================================
# app/routes/__init__.py
# save-state 202602251734 (YYYYMMDDhhmm)
# ========================================== 

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import asyncio
from core.nlp.embeddings import _load_model, get_embedding_async
import logging
from core.map import ledger, centroids
from core.map.mapping_runtime import initialize_runtime


# ------------------- logging setup -------------------
logger = logging.getLogger("peridocs.startup")
# -----------------------------------------------------

# ------------------- static file logging filter -------------------
class FilterStatic(logging.Filter):
    def filter(self, record):
        return "/static/" not in record.getMessage()

logging.getLogger("uvicorn.access").addFilter(FilterStatic())
# -------------------------------------------------------------------


# ********* app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None) is important for not leaving the backend publicly exposed *********
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
logger.info(">>> FASTAPI APP INSTANTIATED FROM app/routes/__init__.py <<<")


@app.on_event("startup")
async def startup_sequence():
    logger.info("Starting application initialization sequence...")

    logger.info("1. Preloading embedding model...")
    await _load_model()
    logger.info("Embedding model loaded.")

    logger.info("2. Initializing mapping runtime...")
    await initialize_runtime(verify=True)
    logger.info("Mapping runtime initialized.")

    logger.info("Startup sequence complete.")


# ---------------- Static Files ----------------
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# ---------------- Import app-bound routes (side effects only) ----------------
from app.routes import info_navigation
from app.routes import entry
from app.routes import feedback

# ---------------- Include router-based routes ----------------
from app.routes import admin_routing
app.include_router(admin_routing.router)

