# ==========================================
# app/routes/authentication_middleware.py
# save-state 2026-05-10T21:33:05-04:00
# ==========================================

from fastapi import Request
from starlette.responses import JSONResponse
from app.credentialing.security_fundamentals import verify_session
from app.credentialing.account_storage import load_accounts


SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


async def auth_middleware(request: Request, call_next):

    path = request.url.path

    # =================================================
    # PUBLIC ROUTES
    # =================================================

    PUBLIC_ROUTES = {
        "/auth/login",
        "/auth/create",
        "/auth/bootstrap/start",
        "/auth/bootstrap/complete",
        "/auth/logout",
        "/favicon.ico",
    }

    PUBLIC_PREFIXES = (
        "/static/",
    )

    is_public = (
        path in PUBLIC_ROUTES
        or any(path.startswith(p) for p in PUBLIC_PREFIXES)
    )

    # =================================================
    # DEFAULT REQUEST AUTH STATE
    # =================================================

    request.state.is_authenticated = False
    request.state.username = None
    request.state.role = None

    # =================================================
    # SESSION PARSE
    # =================================================

    session = request.cookies.get("session")

    if session:

        payload = verify_session(session)

        if payload:

            request.state.is_authenticated = True
            request.state.username = payload["username"]

            accounts = load_accounts()

            user = accounts.get(payload["username"])

            if user:
                request.state.role = user.get("role")

    # =================================================
    # AUTH ENFORCEMENT
    # =================================================

    PROTECTED_PREFIXES = (
        "/admin",
    )

    requires_auth = any(
        path.startswith(p)
        for p in PROTECTED_PREFIXES
    )

    if requires_auth and not is_public:

        if not request.state.is_authenticated:
            return JSONResponse(
                {"detail": "Unauthorized"},
                status_code=401
            )

    # =================================================
    # CSRF CHECK
    # =================================================

    if (
        request.method not in SAFE_METHODS
        and request.state.is_authenticated
    ):

        csrf_cookie = request.cookies.get("csrf_token")

        csrf_header = request.headers.get("X-CSRF-Token")

        if not csrf_cookie or not csrf_header:

            return JSONResponse(
                {"detail": "Missing CSRF token"},
                status_code=403
            )

        if csrf_cookie != csrf_header:

            return JSONResponse(
                {"detail": "Invalid CSRF token"},
                status_code=403
            )

    # =================================================
    # CONTINUE
    # =================================================

    return await call_next(request)