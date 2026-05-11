# ==========================================
# app/routes/__init__.py
# save-state 2026-05-10T22:00:45-04:00 (ISO 8601)
# ========================================== 

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import asyncio
import logging
import sys
import signal
import os
from dotenv import load_dotenv
from pathlib import Path

from fastapi import Request
from fastapi.responses import RedirectResponse, FileResponse, JSONResponse
from app.routes.admin_routing import has_admins
from app.routes import admin_credentialing
from app.credentialing.authentication_middleware import auth_middleware

from core.nlp.embeddings import _load_model, get_embedding_async
from core.map import ledger, centroids
from core.map.mapping_runtime import initialize_runtime
from app.credentialing.account_runtime import (
   initialize_account_runtime,
   shutdown_account_runtime,
)

# ==========================================
# CONFIG Toggle FOR Development VS Production
# ==========================================


ProductionMode = os.getenv("PeriDocs_ProductionMode", "false").strip().lower() == "true"
load_dotenv()

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

from app.routes import donation
app.include_router(donation.router)

app.middleware("http")(auth_middleware)



@app.on_event("startup")
async def startup_sequence():
    logger.info("Starting application initialization sequence...")

    logger.info("1. Preloading embedding model...")
    await _load_model()
    logger.info("Embedding model loaded.")

    logger.info("2. Initializing mapping runtime...")
    await initialize_runtime(verify=True)

    logger.info("3. Initializing account runtime...")
    await initialize_account_runtime()

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
async def admin_bootstrap_funnel(request: Request, call_next):

    path = request.url.path

    if path.startswith("/admin"):

        exists = has_admins()

        # ---------------------------------
        # NO ADMINS YET
        # ---------------------------------

        if not exists:

            if path != "/admin/auth/create":

                return RedirectResponse(
                    "/admin/auth/create",
                    status_code=302
                )

            return await call_next(request)

        # ---------------------------------
        # REQUIRE LOGIN
        # ---------------------------------

        if not request.state.is_authenticated:

            return RedirectResponse(
                "/admin/auth/login",
                status_code=302
            )

        # ---------------------------------
        # REQUIRE ADMIN ROLE
        # ---------------------------------

        if request.state.role != "administrator":

            return JSONResponse(
                {"detail": "Forbidden"},
                status_code=403
            )

    return await call_next(request)

@app.get("/favicon.ico")
def favicon():
    return FileResponse("app/static/peridocs-favicon-2026-05-08.png")