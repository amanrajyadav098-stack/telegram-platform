import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from backend.verification import create_verification, has_valid_access


load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

app = FastAPI(title="Telegram Platform API")


class VerifyRequest(BaseModel):
    telegram_id: int


@app.get("/")
def home():
    return {
        "status": "online",
        "message": "Telegram Platform API is running"
    }


@app.head("/")
def head_home():
    return


@app.post("/verification/create")
def verify_user(request: VerifyRequest):
    expires_at = create_verification(
        DATABASE_URL,
        request.telegram_id
    )

    if expires_at is None:
        raise HTTPException(
            status_code=404,
            detail="User not found"
        )

    return {
        "success": True,
        "telegram_id": request.telegram_id,
        "expires_at": expires_at
    }


@app.get("/verification/status/{telegram_id}")
def verification_status(telegram_id: int):
    valid = has_valid_access(
        DATABASE_URL,
        telegram_id
    )

    return {
        "telegram_id": telegram_id,
        "access_valid": valid
    }