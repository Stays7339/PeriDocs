# ==========================================
# app/credentialing/account_routing.py
# save-state 2026-07-06T17:19-04:00
# ==========================================

import io
import qrcode
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from fastapi.responses import JSONResponse, StreamingResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi import Request, Body
from typing import Optional


from app.credentialing.security_fundamentals import (
    verify_totp_code,
    create_session,
    hash_password,
    verify_password,
    encrypt_value,
    decrypt_value,
    generate_cross_site_request_forgery_token,
    Session_Time_to_Live_in_Seconds,
)

from app.credentialing.account_runtime import account_runtime

logger = logging.getLogger(__name__)



templates = Jinja2Templates(directory="app/templates")

router = APIRouter()




class AccountSignupStartRequest(BaseModel):
    username: str
    password: str


class AccountSignupCompleteRequest(BaseModel):
    signup_token: str
    totp_code: str


class SigninRequest(BaseModel):
    username: str
    password: str
    totp_code: str

class DeleteAccountRequest(BaseModel):
    password: str


# ----------------------------
# Account signup START
# ----------------------------
@router.post("/signup/start")
async def account_signup_start(
    data: AccountSignupStartRequest
):

    result = await (
        account_runtime.begin_account_signup(
            username=data.username,
            password_hash=hash_password(data.password),
        )
    )

    return result


# ----------------------------
# Account signup COMPLETE
# ----------------------------
@router.post("/signup/complete")
async def account_signup_complete(
    request: Request,
    data: AccountSignupCompleteRequest
):

    result = await account_runtime.complete_account_signup(
        signup_token=data.signup_token,
        totp_code=data.totp_code,
    )

    response = JSONResponse({
        "status": "ok",
        "username": result["username"]
    })

    response.set_cookie(
        key="session",
        value=result["session_token"],
        httponly=True,
        secure=request.app.state.production_mode,
        samesite="Strict",
        path="/",
        max_age=Session_Time_to_Live_in_Seconds,
    )

    response.set_cookie(
        key="csrf_token",
        value=result["csrf_token"],
        httponly=False,
        secure=request.app.state.production_mode,
        samesite="Strict",
        path="/",
        max_age=Session_Time_to_Live_in_Seconds,
    )

    return response

# ----------------------------
# signin
# ----------------------------
@router.get("/account")
async def account_page(request: Request):
    return templates.TemplateResponse(
        "account.html",
        {
            "request": request,
            "is_authenticated": request.state.is_authenticated,
            "username": request.state.username,
            "user_role": request.state.role
        }
    )

@router.get("/signup")
async def create_account_page(request: Request):
    return templates.TemplateResponse(
        "account-signup.html",
        {"request": request}
    )

@router.get("/signin")
async def signin_page(request: Request):

    if request.state.is_authenticated:
        return RedirectResponse(url="/account")

    return templates.TemplateResponse(
        "account-signin.html",
        {"request": request}
    )

# router.get is fundamentally different from router.post

@router.post("/signin")
async def signin(request: Request, data: SigninRequest):
    logger.debug(
        "[signin] username=%s",
        data.username
    )

    user = await account_runtime._get_user_object_by_username(
        data.username
    )

    logger.debug(
        "[signin] lookup_result=%r",
        user
    )

    if not user:

        raise HTTPException(
            401,
            "Invalid signin"
        )

    logger.debug(
        "[signin] user=%r",
        user
    )

    if not verify_password(
        user["password_hash"],
        data.password
    ):

        raise HTTPException(
            401,
            "Invalid signin"
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
            "Invalid signin"
        )

    session_token = create_session(user["user_id"])

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
        max_age=Session_Time_to_Live_in_Seconds,
    )

    response.set_cookie(
        key="csrf_token",
        value=csrf_token,
        httponly=False,  # allow JS access for X-CSRF-Token header injection
        secure=request.app.state.production_mode,
        samesite="Strict",
        path="/",
        max_age=Session_Time_to_Live_in_Seconds,
    )

    return response

@router.post("/signout")
def signout():

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

@router.get("/signup/qr")
async def account_signup_qr(
    signup_token: str
):

    pending = (
        await account_runtime.get_pending_signup_snapshot(
            signup_token
        )
    )

    if not pending:

        raise HTTPException(
            404,
            "Invalid signup token"
        )

    username = pending["username"]

    totp_secret = pending[
        "generated_totp_secret"
    ]

    otp_uri = (
        "otpauth://totp/"
        f"PeriDocs:{username}"
        f"?secret={totp_secret}"
        "&issuer=PeriDocs"
    )

    img = qrcode.make(otp_uri)

    buffer = io.BytesIO()

    img.save(buffer, format="PNG")

    buffer.seek(0)

    response = StreamingResponse(
        buffer,
        media_type="image/png"
    )

    response.headers["Cache-Control"] = (
        "no-store"
    )

    return response


@router.post("/account/delete")
async def delete_account(
    request: Request,
    data: DeleteAccountRequest,
):
    # ----------------------------
    # Auth check (middleware also enforces this, but keep as safety net)
    # ----------------------------
    if not request.state.is_authenticated:
        raise HTTPException(401, "Unauthorized")

    user_id = request.state.user_id

    if not user_id:
        raise HTTPException(401, "Unauthorized")

    # ----------------------------
    # Fetch user snapshot
    # ----------------------------
    user = await account_runtime.get_user_snapshot(user_id)


    if not user:
        raise HTTPException(401, "Unauthorized")

    logger.debug("[delete] raw body=%r", await request.body())
    logger.debug("[delete] parsed password=%r", data.password)

    # ----------------------------
    # Password verification
    # ----------------------------
    if not verify_password(
        user["password_hash"],
        data.password
    ):
        raise HTTPException(401, "Invalid password")

    # ----------------------------
    # Perform deletion
    # ----------------------------
    user_id = request.state.user_id
    await account_runtime.delete_account(user_id=user_id)

    # ----------------------------
    # Clear auth cookies
    # ----------------------------
    response = JSONResponse({"status": "account_deleted"})

    response.delete_cookie(key="session", path="/")
    response.delete_cookie(key="csrf_token", path="/")

    return response