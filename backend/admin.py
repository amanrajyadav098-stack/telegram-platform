import os
import psycopg
from dotenv import load_dotenv
from fastapi import APIRouter, Header, HTTPException

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_PANEL_KEY = os.getenv("ADMIN_PANEL_KEY")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not configured")

router = APIRouter(prefix="/admin", tags=["admin"])


def require_admin_key(x_admin_key: str | None) -> None:
    if not ADMIN_PANEL_KEY:
        raise HTTPException(
            status_code=503,
            detail="ADMIN_PANEL_KEY is not configured on the server.",
        )
    if not x_admin_key or x_admin_key != ADMIN_PANEL_KEY:
        raise HTTPException(status_code=401, detail="Invalid admin key.")


@router.post("/reset-all")
def reset_all_verifications(
    x_admin_key: str | None = Header(default=None),
):
    require_admin_key(x_admin_key)

    with psycopg.connect(DATABASE_URL) as conn:
        result = conn.execute(
            """
            UPDATE users
            SET
                is_verified = FALSE,
                access_expires_at = NOW()
            WHERE
                is_verified = TRUE
                OR access_expires_at IS NOT NULL
            """
        )
        conn.commit()

    return {
        "success": True,
        "reset_count": result.rowcount,
        "message": "All verification access has been reset.",
    }
