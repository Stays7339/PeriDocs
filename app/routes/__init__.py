# ==========================================
# app/routes/__init__.py
# save-state 2026-03-24T17:47:05-04:00 (YYYYMMDDhhmm)
# ========================================== 

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import asyncio
import logging
import sys
import signal
from pathlib import Path


from core.nlp.embeddings import _load_model, get_embedding_async
from core.map import ledger, centroids
from core.map.mapping_runtime import initialize_runtime


# ------------------- logging setup -------------------
logger = logging.getLogger("peridocs.app.routes.__init__.py")
logging.basicConfig(
    level=logging.INFO,       # or DEBUG
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
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


# ---------------- Static Files ----------------
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# ---------------- Import app-bound routes (side effects only) ----------------
from app.routes import info_navigation
from app.routes import entry
from app.routes import feedback

# ---------------- Include router-based routes ----------------
from app.routes import admin_routing
app.include_router(admin_routing.router)



@app.on_event("startup")
async def startup_sequence():
    logger.info("Starting application initialization sequence...")

    logger.info("1. Preloading embedding model...")
    await _load_model()
    logger.info("Embedding model loaded.")

    logger.info("2. Initializing mapping runtime...")
    await initialize_runtime(verify=True)

    logger.info("Startup sequence complete.")

@app.on_event("shutdown")
async def cleanup_old_backups():
    """
    Keep only the most recent backup, delete all others.
    Triggered on SIGINT (Ctrl+C) or SIGTERM (systemctl stop).
    """
    backup_dir = Path.cwd() / "backups-for-the-main-data-folder"
    if not backup_dir.exists():
        return

    backups = sorted(backup_dir.glob("peridocs_backup_*.zip"), reverse=True)
    # Keep the most recent
    to_delete = backups[1:]
    for f in to_delete:
        try:
            f.unlink()
            logger.info(f"[shutdown] Deleted old backup: {f.name}")
        except Exception as e:
            logger.warning(f"[shutdown] Failed to delete {f.name}: {e}")
