# ==========================================
# app/credentialing/account_routing.py
# save-state 2026-05-20T20:48:20-04:00
# ==========================================

import io
import qrcode
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from fastapi import Request



from app.credentialing.security_fundamentals import (
    verify_totp_code,
    create_session,
    hash_password,
    verify_password,
    encrypt_value,
    decrypt_value,
    generate_cross_site_request_forgery_token,
)

from app.credentialing.account_runtime import account_runtime

templates = Jinja2Templates(directory="app/templates")

router = APIRouter()




class AccountSetupStartRequest(BaseModel):
    username: str
    password: str


class AccountSetupCompleteRequest(BaseModel):
    setup_token: str
    totp_code: str


class LoginRequest(BaseModel):
    username: str
    password: str
    totp_code: str


# ----------------------------
# Account Setup START
# ----------------------------
@router.post("/account/setup/start")
async def account_setup_start(
    data: AccountSetupStartRequest
):

    result = await (
        account_runtime.begin_account_setup(
            username=data.username,
            password_hash=hash_password(data.password),
        )
    )

    return result


# ----------------------------
# Account Setup COMPLETE
# ----------------------------
@router.post("/account/setup/complete")
async def account_setup_complete(
    data: AccountSetupCompleteRequest
):

    await (
        account_runtime.complete_account_setup(
            setup_token=data.setup_token,
            totp_code=data.totp_code,
        )
    )

    return {
        "status": "ok"
    }


# ----------------------------
# LOGIN
# ----------------------------
@router.get("/signup")
async def create_account_page(request: Request):
    return templates.TemplateResponse(
        "account-setup.html",
        {"request": request}
    )

@router.get("/signin")
async def login_page(request: Request):
    return templates.TemplateResponse(
        "account-login.html",
        {"request": request}
    )

# router.get is fundamentally different from router.post

@router.post("/signin")
async def login(request: Request, data: LoginRequest):

    user = await (
        account_runtime.get_user_snapshot(
            data.username
        )
    )

    if not user:

        raise HTTPException(
            401,
            "Invalid login"
        )

    if not verify_password(
        user["password_hash"],
        data.password
    ):

        raise HTTPException(
            401,
            "Invalid login"
        )

    totp_secret = decrypt_value(
        user["totp_secret_encrypted"]
    )

    if not verify_totp_code(
        totp_secret,
        data.totp_code
    ):

        raise HTTPException(
            401,
            "Invalid login"
        )

    session_token = create_session(user["username"])

    csrf_token = (
        generate_cross_site_request_forgery_token()
    )

    response = JSONResponse({
        "status": "ok"
    })

    response.set_cookie(
        key="session",
        value=session_token,
        httponly=True, # httponly=True JavaScript cannot read the cookie at all.
        secure=request.app.state.production_mode,
        samesite="Strict", # Prevents cookie interception on unencrypted networks. The cookie is ONLY sent over HTTPS, never HTTP.
        path="/",
        max_age=604800,
    )

    response.set_cookie(
        key="csrf_token",
        value=csrf_token,
        httponly=True, #
        secure=request.app.state.production_mode,
        samesite="Strict",
        path="/",
        max_age=604800,
    )

    return response

@router.post("/signout")
def logout():

    response = JSONResponse({
        "status": "logged_out"
    })

    response.delete_cookie(
        key="session",
        path="/"
    )

    response.delete_cookie(
        key="csrf_token",
        path="/"
    )   

    return response

@router.get("/account/setup/qr")
def account_setup_qr(uri: str):

    img = qrcode.make(uri)

    buffer = io.BytesIO()

    img.save(buffer, format="PNG")

    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="image/png"
    )