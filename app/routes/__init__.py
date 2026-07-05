# ==========================================
# app/routes/__init__.py
# save-state 2026-07-05T15:23-04:00 (ISO 8601)
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
from app.credentialing.authentication_middleware import (
    auth_middleware,
    security_headers_middleware,
)
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware


from app.credentialing import account_routing
from app.credentialing.account_runtime import (
    account_runtime,
    initialize_account_runtime,
    shutdown_account_runtime,
)
from core.nlp.embeddings import _load_model, get_embedding_async
from core.map import ledger, centroids
from core.map.mapping_runtime import initialize_runtime
from core.database import initialize_database, close_database



# ------------------- logging setup -------------------
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.DEBUG,
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
# for a cautious example, enabling /openapi.json becomes a full system map of all internal routes.
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
logger.info(">>> FASTAPI APP INSTANTIATED FROM app/routes/__init__.py <<<")

# ==========================================
# CONFIG Toggle FOR Development VS Production
# ==========================================

load_dotenv()
ProductionMode = os.getenv("PeriDocs_ProductionMode", "false").strip().lower() == "true"

logger.warning("ProductionMode=%s", ProductionMode)

app.state.production_mode = ProductionMode
templates = Jinja2Templates(directory="app/templates")
templates.env.globals["ProductionMode"] = ProductionMode


# ---------------- Static Files ----------------
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# ---------------- Import app-bound routes (side effects only) ----------------
from app.routes import info_navigation
from app.routes import submission_routing
from app.routes import feedback

# ---------------- Include router-based routes ----------------

from app.routes import admin_routing
app.include_router(admin_routing.router)
app.include_router(account_routing.router)

from app.routes import donation
app.include_router(donation.router)


# ---------------- CORS (comes in handy once API and forked instances happen) ----------------

ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)




"""
CSP (Content Security Policy) generally asks:
“Considering everything across the open internet, what scripts/resources is this page allowed to load and execute at all?”
CSP is enforced by the browser on your own page. 
CSP primarily protects against malicious code executing inside your own pages.

CORS (Cross-Origin Resource Sharing):
“Which outside websites are allowed to talk to this website through the user's browser?”
CORS policy only affects how browsers handle requests to PeriDocs itself.
CORS mainly controls whether browser JavaScript may READ the response sent between origins.
This becomes important once the PeriDocs project folder is public, mainly for API calls and forkable policy decisions.

CSRF (Cross-Site Request Forgery) generally asks:
“Was this request intentionally made from the real site session, instead of another site secretly using the user’s signin cookies?”
CSRF protection is enforced by your backend when accepting sensitive requests.
It helps protect against mistakenly trusting the API requests, even if the attacker cannot usually read responses.

HttpOnly = “JavaScript cannot read or steal the proof”
Secure = “The proof is only sent over HTTPS connections” Also, this doesn't matter if the force_https_in_production function is not active in the code.

"""

# ------------------------------------------------

app.middleware("http")(auth_middleware)
app.middleware("http")(security_headers_middleware)




@app.on_event("startup")
async def startup_sequence():
    logger.info("Starting application initialization sequence...")

    logger.info("0. Initializing database connectivity layer...")
    await initialize_database()

    logger.info("1. Preloading embedding model...")
    await _load_model()
    logger.info("Embedding model loaded.")

    logger.info("2. Initializing mapping runtime...")
    await initialize_runtime(verify=True)

    logger.info("3. Initializing account runtime...")
    await initialize_account_runtime()

    logger.info("Startup sequence complete.")

@app.on_event("shutdown")
async def shutdown_sequence():
    logger.info("Starting shutdown sequence...")

    # 1. Authoritatively flush and close the entry runtime while DB connections are still hot
    try:
        from core.map.mapping_runtime import entry_runtime
        logger.info("Draining entry runtime memory layers to database...")
        
        # Invoke standard shutdown routine first
        await entry_runtime.shutdown()
        
        # FORCE an unconditional guarded flush to catch entries orphaned by the dirty counter race condition
        logger.warning("[SHUTDOWN FIX] Forcing unconditional guarded persist of all memory states...")
        if hasattr(entry_runtime, '_persist_guarded'):
            await entry_runtime._persist_guarded()
        elif hasattr(entry_runtime, '_persist'):
            await entry_runtime._persist()
            
    except Exception as e:
        logger.error("Failed to safely flush entry runtime during shutdown: %s", e)

    # 2. Shutdown your account runtime tracking
    try:
        await shutdown_account_runtime()
    except Exception as e:
        logger.error("Failed to shutdown account runtime: %s", e)

    # 3. Always drain and close database connection pools safely
    logger.info("Draining database connections...")
    try:
        await close_database()
    except Exception as e:
        logger.error("Error occurred while closing database engine: %s", e)

    # 4. Handle file system backup house-cleaning (isolated so it can't block core components)
    """
    Keep only the most recent backup, delete all others.
    Triggered on SIGINT (Ctrl+C) or SIGTERM (systemctl stop).
    """
    backup_dir = Path.cwd() / "backups-for-the-main-data-folder"
    if backup_dir.exists():
        backups = sorted(backup_dir.glob("peridocs_data_folder_backup_*.zip"), reverse=True)
        to_delete = backups[1:]
        for f in to_delete:
            try:
                f.unlink()
                logger.info(f"[shutdown] Deleted old backup: {f.name}")
            except Exception as e:
                logger.warning(f"[shutdown] Failed to delete {f.name}: {e}")
    else:
        logger.debug("[shutdown] Backup directory not found, skipping zip pruning.")

@app.get("/favicon.ico")
def favicon():
    return FileResponse("app/static/peridocs-favicon-2026-05-08.png")