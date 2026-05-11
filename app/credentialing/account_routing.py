# ==========================================
# app/credentialing/account_routing.py
# save-state 2026-05-10T21:32:35-04:00
# ==========================================


import io
import qrcode
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from fastapi.responses import JSONResponse, StreamingResponse


from app.credentialing.account_storage import load_accounts, save_accounts
from app.credentialing.create_first_account import (
    create_bootstrap_ticket,
    verify_bootstrap_ticket,
    consume_bootstrap_ticket
)
from app.credentialing.security_fundamentals import (
    verify_time_code,
    create_session,
    hash_password,
    verify_password,
    encrypt_value,
    decrypt_value,
    generate_cross_site_request_forgery_token,
)

templates.env.globals["ProductionMode"] = ProductionMode

router = APIRouter(prefix="/auth")


class BootstrapRequest(BaseModel):
    username: str
    password: str


class BootstrapCompleteRequest(BaseModel):
    ticket_id: str
    password: str
    time_code: str


class LoginRequest(BaseModel):
    username: str
    password: str
    time_code: str


# ----------------------------
# BOOTSTRAP START
# ----------------------------
@router.post("/bootstrap/start")
def bootstrap_start(data: BootstrapRequest):

    accounts = load_accounts()

    if accounts:
        raise HTTPException(403, "System already initialized")

    ticket_id, temp_secret = create_bootstrap_ticket(data.username)

    return {
        "ticket_id": ticket_id,
        "time_code_secret": temp_secret
    }


# ----------------------------
# BOOTSTRAP COMPLETE
# ----------------------------
@router.post("/bootstrap/complete")
def bootstrap_complete(data: BootstrapCompleteRequest):

    ticket = verify_bootstrap_ticket(data.ticket_id)

    if not verify_time_code(ticket["temp_secret"], data.time_code):
        raise HTTPException(401, "Invalid time-based code")

    accounts = load_accounts()

    if accounts:
        raise HTTPException(403, "System already initialized")

    role = "administrator" if len(accounts) == 0 else "ordinary"

    accounts[ticket["username"]] = {
        "password_hash": hash_password(data.password),  # NOTE: should be hashed in final pass
        "time_secret_encrypted": encrypt_value(ticket["temp_secret"]),
        "role": role
    }

    save_accounts(accounts)

    consume_bootstrap_ticket(data.ticket_id)

    return {"status": "ok"}


# ----------------------------
# LOGIN
# ----------------------------
@router.post("/login")
def login(data: LoginRequest):

    accounts = load_accounts()
    user = accounts.get(data.username)

    if not user:
        raise HTTPException(401, "Invalid login")

    if not verify_password(user["password_hash"], data.password):
        raise HTTPException(401, "Invalid login")

    time_secret = decrypt_value(
        user["time_secret_encrypted"]
    )

    if not verify_time_code(time_secret, data.time_code):
        raise HTTPException(401, "Invalid login")
    
    session_token = create_session(data.username)
    csrf_token = generate_cross_site_request_forgery_token()

    response = JSONResponse({
        "status": "ok"
    })

    response.set_cookie(
        key="session",
        value=session_token,

        # JavaScript cannot read cookie. 
        # HttpOnly=True actually means: “This cookie may only be accessed by the browser’s network layer, 
        # not by JavaScript.”
        # It's not actually making the login info explicitly unencrypted, 
        # though it doesn't automatically add in encryption either (which would be HTTPS / secure=true)
        httponly=True,

        # only send over HTTPS in production
        secure=ProductionMode,

        # blocks most cross-site abuse
        samesite="strict",

        # cookie available site-wide
        path="/",

        # one hour
        max_age=3600
    )

    response.set_cookie(
        key="csrf_token",
        value=csrf_token,

        httponly=False,

        secure=ProductionMode,

        samesite="strict",

        path="/",

        max_age=3600
    )

    return response

@router.post("/logout")
def logout():

    response = JSONResponse({
        "status": "logged_out"
    })

    response.delete_cookie(
        key="session",
        key="csrf_token",
        path="/"
    )

    return response

@router.get("/bootstrap/qr")
def bootstrap_qr(uri: str):

    img = qrcode.make(uri)

    buffer = io.BytesIO()

    img.save(buffer, format="PNG")

    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="image/png"
    )