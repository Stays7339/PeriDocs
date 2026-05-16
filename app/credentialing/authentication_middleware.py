# ==========================================
# app/routes/authentication_middleware.py
# save-state 2026-05-16T12:28:40-04:00
# ==========================================

from fastapi import Request
from starlette.responses import JSONResponse
from app.credentialing.security_fundamentals import verify_session
from app.credentialing.account_runtime import account_runtime


SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


async def auth_middleware(request: Request, call_next):

    path = request.url.path

    # =================================================
    # PUBLIC ROUTES
    # =================================================

    PUBLIC_ROUTES = {
        "/signin",
        "/signup",
        "/signup/start",
        "/signup/complete",
        "/signout",
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

            user = await account_runtime.get_user_snapshot(payload["username"])

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

    if requires_auth:

        if not request.state.is_authenticated:

            return JSONResponse(
                {"detail": "Unauthorized"},
                status_code=401
            )

        if request.state.role != "administrator":

            return JSONResponse(
                {"detail": "Not found"},
                status_code=404
            )

    # =================================================
    # CSRF CHECK
    # =================================================

    """

    HttpOnly and Secure protect the cookie itself (storage and transport constraints).
    CSRF () protects server actions that rely on those cookies.
    CORS protects cross-origin / cross-website JavaScript from reading server responses.
    CSP protects what your webpage is allowed to execute or load, mainly to avoid unrecognized javascript.

    ----
    Cookies = “Proof of login automatically attached by the browser when talking to your server”

    HttpOnly = “JavaScript cannot read or steal the proof”
    Secure = “The proof is only sent over HTTPS connections”

    CSRF (Cross-Site Request Forgery)
    “Can another website trick the browser into sending a request using your proof without your intent?”

    CORS (Cross-Origin Resource Sharing)
    “Can JavaScript running on another website/URL read responses from this server in the browser?”

    CSP (Content Security Policy) = “Considering everything across the open internet, what scripts/resources is this page allowed to load and execute at all?”

    The browser enforces CORS, CSP, HttpOnly, and Secure.
    The backend enforces CSRF (and session validation).
    """

    if (
        request.method not in SAFE_METHODS
        and request.state.is_authenticated
    ):

        CSRF_EXEMPT_ROUTES = {
            "/auth/account/setup/start",
            "/auth/account/setup/complete",
        }

        if path not in CSRF_EXEMPT_ROUTES:

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

    response = await call_next(request)

    return response

async def security_headers_middleware(request, call_next):

    response = await call_next(request)

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


    return response