# ==========================================
# app/routes/authentication_middleware.py
# save-state 2026-06-03T22:39-04:00
# ==========================================

from fastapi import Request
from starlette.responses import JSONResponse
from app.credentialing.security_fundamentals import verify_session
from app.credentialing.account_runtime import account_runtime

import secrets  # (used for CSRF token generation)
import logging
import uuid

logger = logging.getLogger(__name__)

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

async def auth_middleware(request: Request, call_next):

    request_id = uuid.uuid4().hex
    request.state.request_id = request_id

    # logger.debug("[auth_middware][ENTER] request_id=%s path=%s", request_id, request.url.path)

    # logger.debug("[auth_middware()] ACCOUNT_RUNTIME_ID=%s", id(account_runtime))

    """
    # according to an LLM conversation on 2026-05-03
    # multiple requests fire on page load (/, /account, /favicon.ico, etc.)
    # frontend is doing several fetch calls in parallel
    # middleware runs per-request (so logging repeats naturally)
    """

    path = request.url.path

    SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

    # ----------------------------
    # AUTH STATE DEFAULTS
    # ----------------------------
    request.state.is_authenticated = False
    request.state.user_id = None
    request.state.username = None
    request.state.role = None

    session = request.cookies.get("session")

    if session:
        payload = verify_session(session)
        logger.debug("SESSION PAYLOAD: %s", payload)

        if payload:
            user = await account_runtime.get_user_snapshot(payload["user_id"])
            logger.debug("USER LOOKUP RESULT: %s", user)

            if user:
                request.state.is_authenticated = True
                request.state.user_id = payload["user_id"]
                request.state.role = user.get("role")
                request.state.username = user.get("username")

    # ----------------------------
    # AUTH ENFORCEMENT
    # ----------------------------
    PROTECTED_PREFIXES = ("/admin",)

    if any(path.startswith(p) for p in PROTECTED_PREFIXES):

        if not request.state.is_authenticated:
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)

        if request.state.role != "administrator":
            return JSONResponse({"detail": "Not found"}, status_code=404)

    # ----------------------------
    # CSRF VALIDATION (ONLY FOR NON-SAFE METHODS)
    # ----------------------------
    if request.method not in SAFE_METHODS:

        csrf_cookie_value = request.cookies.get("csrf_token")
        csrf_header_value = request.headers.get("X-CSRF-Token")

        if not csrf_cookie_value or not csrf_header_value:
            return JSONResponse({"detail": "Missing CSRF token"}, status_code=403)

        if csrf_cookie_value != csrf_header_value:
            return JSONResponse({"detail": "Invalid CSRF token"}, status_code=403)

    response = await call_next(request)

    # logger.debug("[auth_middware][EXIT] request_id=%s path=%s", request_id, request.url.path)

    return response


async def security_headers_middleware(request: Request, call_next):

    response = await call_next(request)

    if response is None:
        return JSONResponse({"detail": "Internal server error"}, status_code=500)

    # ----------------------------
    # SECURITY HEADERS
    # ----------------------------
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "font-src 'self'; "
        "connect-src 'self'; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "frame-ancestors 'none';"
    )

    # ----------------------------
    # CSRF ISSUANCE (SAFE BOOTSTRAP)
    # ----------------------------
    existing_csrf_token = request.cookies.get("csrf_token")

    if not existing_csrf_token:

        fresh_token = secrets.token_urlsafe(32)

        response.set_cookie(
            key="csrf_token",
            value=fresh_token,
            httponly=False,
            secure=request.app.state.production_mode,
            samesite="lax",
            path="/",
        )

    return response