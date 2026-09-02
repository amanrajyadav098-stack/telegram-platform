from datetime import datetime, timedelta, timezone
import hashlib
import hmac

import psycopg


def create_verification_token(telegram_id: int, secret: str) -> str:
    timestamp = str(int(datetime.now(timezone.utc).timestamp()))

    payload = f"{telegram_id}:{timestamp}"

    signature = hmac.new(
        secret.encode(),
        payload.encode(),
        hashlib.sha256
    ).hexdigest()

    return f"{telegram_id}:{timestamp}:{signature}"


def verify_token(
    token: str,
    secret: str,
    max_age: int = 600
) -> int | None:
    try:
        telegram_id, timestamp, signature = token.split(":", 2)

        payload = f"{telegram_id}:{timestamp}"

        expected_signature = hmac.new(
            secret.encode(),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(
            signature,
            expected_signature
        ):
            return None

        token_time = int(timestamp)
        now = int(
            datetime.now(timezone.utc).timestamp()
        )

        if now - token_time > max_age:
            return None

        return int(telegram_id)

    except (ValueError, TypeError):
        return None


def create_verification(
    database_url: str,
    telegram_id: int,
    method: str = "website"
):
    with psycopg.connect(database_url) as conn:
        user = conn.execute(
            """
            SELECT id
            FROM users
            WHERE telegram_id = %s
            """,
            (telegram_id,),
        ).fetchone()

        if user is None:
            return None

        user_id = user[0]

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=20)

        conn.execute(
            """
            UPDATE users
            SET is_verified = TRUE,
                access_expires_at = %s,
                updated_at = NOW()
            WHERE id = %s
            """,
            (expires_at, user_id),
        )

        conn.execute(
            """
            INSERT INTO verifications
                (
                    user_id,
                    verified_at,
                    expires_at,
                    verification_method
                )
            VALUES (%s, %s, %s, %s)
            """,
            (
                user_id,
                now,
                expires_at,
                method,
            ),
        )

        return expires_at


def has_valid_access(
    database_url: str,
    telegram_id: int
) -> bool:
    with psycopg.connect(database_url) as conn:
        row = conn.execute(
            """
            SELECT is_verified, access_expires_at
            FROM users
            WHERE telegram_id = %s
            """,
            (telegram_id,),
        ).fetchone()

        if row is None:
            return False

        is_verified, expires_at = row

        if not is_verified or expires_at is None:
            return False

        return expires_at > datetime.now(timezone.utc)