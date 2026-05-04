# ==========================================
# app/routes/donation.py
# Routing PeriDocs Users to Stripe for Donations to PeriDocs
# save-state 2026-05-04T00:22:45-04:00
# ==========================================

import os
import stripe
import logging
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from dotenv import load_dotenv


# -----------------------------
# Logging (consistent with your system)
# -----------------------------
logger = logging.getLogger(__name__)


# -----------------------------
# Load .env from project root (PeriDocs/.env)
# -----------------------------
BASE_DIR = Path(__file__).resolve().parents[2]  # -> PeriDocs/
ENV_PATH = BASE_DIR / ".env"

load_dotenv(dotenv_path=ENV_PATH)


# -----------------------------
# Stripe init (NO hardcoding secrets)
# -----------------------------
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")

if not STRIPE_SECRET_KEY:
    logger.warning("Stripe secret key not found in .env")

stripe.api_key = STRIPE_SECRET_KEY


# -----------------------------
# Core config
# -----------------------------
STRIPE_PRODUCT_ID = os.getenv("STRIPE_PRODUCT_ID") 

if not STRIPE_PRODUCT_ID:
    logger.warning("STRIPE_PRODUCT_ID not set in .env (required for subscriptions)")


router = APIRouter()


# ==========================================
# CREATE SUBSCRIPTION (dynamic monthly donation)
# ==========================================
@router.post("/donation/create-subscription")
async def create_subscription(request: Request):
    """
    Creates a Stripe Checkout Session for a recurring monthly donation.
    No user identity is stored on PeriDocs side.
    """

    try:
        data = await request.json()
        amount = float(data.get("amount", 0))

        # -----------------------------
        # Guardrails (important for abuse + mistakes)
        # -----------------------------
        if amount < 1:
            return JSONResponse(
                {"status": "error", "message": "Minimum monthly donation is $1"},
                status_code=400
            )

        if amount > 1000:
            return JSONResponse(
                {"status": "error", "message": "Maximum monthly donation is $1000"},
                status_code=400
            )

        amount_cents = int(amount * 100)

        # -----------------------------
        # Stripe Checkout Session
        # (subscription mode = recurring billing)
        # -----------------------------
        session = stripe.checkout.Session.create(
            mode="subscription",
            payment_method_types=["card"],
            line_items=[
                {
                    "price_data": {
                        "currency": "usd",
                        "unit_amount": amount_cents,
                        "recurring": {
                            "interval": "month"
                        },
                        "product_data": {
                            "name": "PeriDocs Monthly Donation",
                            "description": "Thank you for supporting us! PeriDocs LLC is a small team of two people, and we are not a 501(c)(3) organization, so donations are not tax-deductible. Transactions are entirely handled by Stripe, our payment processor."
                        },
                    },
                    "quantity": 1
                }
            ],

            # Stripe-hosted redirect flow
            success_url="https://peridocs.org/",
            cancel_url="https://peridocs.org/",

            consent_collection={
                "terms_of_service": "required"
            },

            custom_text={
                "terms_of_service_acceptance": {
                    "message": "Thank you! PeriDocs LLC is not a 501(c)(3) organization, so donations are not tax-deductible. Payment processed by Stripe."
                }
            },

            # Keep metadata minimal (no user identity storage)
            metadata={
                "source": "peridocs_monthly_donation",
                "type": "monthly",
                "amount_usd": str(amount)
            }
        )

        return JSONResponse({
            "status": "success",
            "payment_status": session.payment_status,
            "url": session.url,
            "mode": session.mode
        })

    except Exception as e:
        logger.exception("Stripe subscription creation failed")
        return JSONResponse(
            {"status": "error", "message": "Unable to create subscription session"},
            status_code=500
        )


# ==========================================
# CREATE ONE-TIME DONATION
# ==========================================
@router.post("/donation/create-onetime")
async def create_onetime_donation(request: Request):
    """
    One-time donation via Stripe Checkout.
    """

    try:
        data = await request.json()
        amount = float(data.get("amount", 0))

        if amount < 1:
            return JSONResponse(
                {"status": "error", "message": "Minimum donation is $1"},
                status_code=400
            )

        if amount > 5000:
            return JSONResponse(
                {"status": "error", "message": "Maximum donation is $5000"},
                status_code=400
            )

        amount_cents = int(amount * 100)

        session = stripe.checkout.Session.create(
            mode="payment",
            customer_creation="always",
            payment_method_types=["card"],
            line_items=[
                {
                    "price_data": {
                        "currency": "usd",
                        "unit_amount": amount_cents,
                        "product_data": {
                            "name": "PeriDocs One-Time Donation",
                            "description": "Thank you for supporting us! PeriDocs LLC is a small team of two people, and we are not a 501(c)(3) organization, so donations are not tax-deductible. Transactions are entirely handled by Stripe, our payment processor."
                        },
                    },
                    "quantity": 1,
                }
            ],
            success_url="https://peridocs.org/",
            cancel_url="https://peridocs.org/",

            consent_collection={
                "terms_of_service": "required"
            },

            custom_text={
                "terms_of_service_acceptance": {
                    "message": "Thank you! PeriDocs LLC is not a 501(c)(3) organization, so donations are not tax-deductible. Payment processed by Stripe."
                }
            },

            metadata={
                "source": "peridocs_onetime_donation",
                "type": "ontime",
                "amount_usd": str(amount)
            }
        )

        return JSONResponse({
            "status": "success",
            "payment_status": session.payment_status,
            "url": session.url,
            "mode": session.mode
        })

    except Exception:
        logger.exception("Stripe one-time donation failed")
        return JSONResponse(
            {"status": "error", "message": "Unable to create donation session"},
            status_code=500
        )


# ==========================================
# SUCCESS PAGE HANDLER (no state stored)
# ==========================================
@router.get("/donation/success")
async def donation_success(session_id: str):
    """
    Optional endpoint:
    purely informational; pulls session data from Stripe if needed.
    """

    try:
        session = stripe.checkout.Session.retrieve(session_id)

        return JSONResponse({
            "status": "success",
            "payment_status": session.payment_status,
            "mode": session.mode
        })

    except Exception:
        return JSONResponse(
            {"status": "success"},
            status_code=200
        )