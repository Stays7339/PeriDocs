# ==========================================
# app/routes/__init__.py
# save-state 2026-05-03T13:18:00-04:00 (ISO 8601)
# ========================================== 

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import asyncio
import logging
import sys
import signal
from pathlib import Path

from fastapi import Request
from fastapi.responses import RedirectResponse, FileResponse
from app.routes.admin_routing import has_admins
from app.routes import admin_credentialing


from core.nlp.embeddings import _load_model, get_embedding_async
from core.map import ledger, centroids
from core.map.mapping_runtime import initialize_runtime


# ------------------- logging setup -------------------
logger = logging.getLogger(__name__)
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
app.include_router(admin_credentialing.router) 



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

    backups = sorted(backup_dir.glob("peridocs_data_folder_backup_*.zip"), reverse=True)
    # Keep the most recent
    to_delete = backups[1:]
    for f in to_delete:
        try:
            f.unlink()
            logger.info(f"[shutdown] Deleted old backup: {f.name}")
        except Exception as e:
            logger.warning(f"[shutdown] Failed to delete {f.name}: {e}")


@app.middleware("http")
async def admin_bootstrap_gate(request: Request, call_next):
    path = request.url.path

    
    if path.startswith("/admin"):

        exists = has_admins()

        # NEW: check session cookie
        cookie = request.cookies.get("admin_session")
        is_logged_in = admin_credentialing.verify_session(cookie) if cookie else False

        # allow auth routes always
        if path.startswith("/admin/auth"):
            return await call_next(request)

        # no admins → bootstrap
        if not exists and path != "/admin/auth/create":
            return RedirectResponse("/admin/auth/create")

        # admins exist but not logged in → force login
        if exists and not is_logged_in:
            return RedirectResponse("/admin/auth/login")

    return await call_next(request)

@app.get("/favicon.ico")
def favicon():
    return FileResponse("app/static/favicon.png")