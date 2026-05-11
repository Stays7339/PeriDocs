# ==========================================
# app/credentialing/account_routing.py
# save-state 2026-05-11T14:18:55-04:00
# ==========================================


import io
import qrcode
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from fastapi.responses import JSONResponse, StreamingResponse



from app.credentialing.security_fundamentals import (
    verify_time_code,
    create_session,
    hash_password,
    verify_password,
    encrypt_value,
    decrypt_value,
    generate_cross_site_request_forgery_token,
)

from app.credentialing.account_runtime import account_runtime

templates.env.globals.setdefault(
    "ProductionMode",
    request.app.state.production_mode
)

router = APIRouter(prefix="/auth")


class AccountSetupStartRequest(BaseModel):
    username: str
    password: str


class AccountSetupCompleteRequest(BaseModel):
    setup_token: str
    time_code: str


class LoginRequest(BaseModel):
    username: str
    password: str
    time_code: str


# ----------------------------
# BOOTSTRAP START
# ----------------------------
@router.post("/account/setup/start")
async def account_setup_start(
    data: AccountSetupStartRequest
):

    result = await (
        account_runtime.begin_account_setup(
            username=data.username,
            plaintext_password=data.password,
        )
    )

    return result


# ----------------------------
# BOOTSTRAP COMPLETE
# ----------------------------
@router.post("/account/setup/complete")
async def account_setup_complete(
    data: AccountSetupCompleteRequest
):

    await (
        account_runtime.complete_account_setup(
            setup_token=data.setup_token,
            submitted_totp_code=data.time_code,
        )
    )

    return {
        "status": "ok"
    }


# ----------------------------
# LOGIN
# ----------------------------
@router.post("/login")
async def login(data: LoginRequest):

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

    time_secret = decrypt_value(
        user["time_secret_encrypted"]
    )

    if not verify_time_code(
        time_secret,
        data.time_code
    ):

        raise HTTPException(
            401,
            "Invalid login"
        )

    session_token = create_session({
        "user_id":
            user["user_id"],

        "username":
            user["username"],
    })

    csrf_token = (
        generate_cross_site_request_forgery_token()
    )

    response = JSONResponse({
        "status": "ok"
    })

    templates.env.globals.setdefault(
        "ProductionMode",
        request.app.state.production_mode
    )

    response.set_cookie(
        key="session",
        value=session_token,
        httponly=True,
        secure=production_mode,
        samesite="Lax",
        path="/",
        max_age=604800,
    )

    response.set_cookie(
        key="csrf_token",
        value=csrf_token,
        httponly=False,
        secure=production_mode,
        samesite="Lax",
        path="/",
        max_age=604800,
    )

    return response

@router.post("/logout")
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