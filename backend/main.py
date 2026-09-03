import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.verification import (
    create_verification,
    has_valid_access,
    verify_token,
)

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
VERIFICATION_SECRET = os.getenv("VERIFICATION_SECRET")

app = FastAPI(
    title="Telegram Platform API"
)


# =========================================================
# CORS
# =========================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://telegram-platform-omega.vercel.app",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================================================
# REQUEST MODELS
# =========================================================

class VerifyRequest(BaseModel):
    telegram_id: int


class TokenVerifyRequest(BaseModel):
    token: str


# =========================================================
# HOME
# =========================================================

@app.get("/")
def home():
    return {
        "status": "online",
        "message": "Telegram Platform API is running",
    }


@app.head("/")
def head_home():
    return


# =========================================================
# DIRECT VERIFICATION
# =========================================================

@app.post("/verification/create")
def verify_user(request: VerifyRequest):

    expires_at = create_verification(
        DATABASE_URL,
        request.telegram_id,
    )

    if expires_at is None:
        raise HTTPException(
            status_code=404,
            detail="User not found",
        )

    return {
        "success": True,
        "telegram_id": request.telegram_id,
        "expires_at": expires_at,
    }


# =========================================================
# TOKEN VERIFICATION
# =========================================================

@app.post("/verification/complete")
def complete_verification(
    request: TokenVerifyRequest,
):

    if not VERIFICATION_SECRET:
        raise HTTPException(
            status_code=500,
            detail="Verification secret is not configured",
        )

    telegram_id = verify_token(
        request.token,
        VERIFICATION_SECRET,
    )

    if telegram_id is None:
        raise HTTPException(
            status_code=400,
            detail="Invalid or expired verification token",
        )

    expires_at = create_verification(
        DATABASE_URL,
        telegram_id,
        method="website",
    )

    if expires_at is None:
        raise HTTPException(
            status_code=404,
            detail="User not found",
        )

    return {
        "success": True,
        "telegram_id": telegram_id,
        "expires_at": expires_at,
    }


# =========================================================
# VERIFICATION STATUS
# =========================================================

@app.get("/verification/status/{telegram_id}")
def verification_status(
    telegram_id: int,
):

    valid = has_valid_access(
        DATABASE_URL,
        telegram_id,
    )

    return {
        "telegram_id": telegram_id,
        "access_valid": valid,
    }