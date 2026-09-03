import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import hmac

import psycopg
from psycopg_pool import ConnectionPool


_pool = None


def get_pool(database_url: str) -> ConnectionPool:
    global _pool

    if _pool is None:
        _pool = ConnectionPool(
            conninfo=database_url,
            min_size=1,
            max_size=8,
            timeout=10,
        )

    return _pool


def close_pool():
    global _pool

    if _pool is not None:
        _pool.close()
        _pool = None


def create_verification_token(
    telegram_id: int,
    secret: str,
) -> str:
    timestamp = str(
        int(datetime.now(timezone.utc).timestamp())
    )

    payload = f"{telegram_id}:{timestamp}"

    signature = hmac.new(
        secret.encode(),
        payload.encode(),
        hashlib.sha256,
    ).hexdigest()

    return f"{telegram_id}:{timestamp}:{signature}"


def verify_token(
    token: str,
    secret: str,
    max_age: int = 600,
) -> int | None:
    try:
        telegram_id, timestamp, signature = token.split(
            ":",
            2,
        )

        payload = f"{telegram_id}:{timestamp}"

        expected_signature = hmac.new(
            secret.encode(),
            payload.encode(),
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(
            signature,
            expected_signature,
        ):
            return None

        token_time = int(timestamp)

        now = int(
            datetime.now(timezone.utc).timestamp()
        )

        if now - token_time > max_age:
            return None

        if now < token_time:
            return None

        return int(telegram_id)

    except (ValueError, TypeError):
        return None


def _ensure_user_sync(
    database_url: str,
    telegram_id: int,
    username: str | None = None,
    first_name: str | None = None,
):
    pool = get_pool(database_url)

    with pool.connection() as conn:
        conn.execute(
            """
            INSERT INTO users (
                telegram_id,
                username,
                first_name
            )
            VALUES (%s, %s, %s)
            ON CONFLICT (telegram_id)
            DO UPDATE SET
                username = COALESCE(
                    EXCLUDED.username,
                    users.username
                ),
                first_name = COALESCE(
                    EXCLUDED.first_name,
                    users.first_name
                ),
                updated_at = NOW()
            """,
            (
                telegram_id,
                username,
                first_name,
            ),
        )

        conn.commit()


def ensure_user(
    database_url: str,
    telegram_id: int,
    username: str | None = None,
    first_name: str | None = None,
):
    return _ensure_user_sync(
        database_url,
        telegram_id,
        username,
        first_name,
    )


async def ensure_user_async(
    database_url: str,
    telegram_id: int,
    username: str | None = None,
    first_name: str | None = None,
):
    await asyncio.to_thread(
        _ensure_user_sync,
        database_url,
        telegram_id,
        username,
        first_name,
    )


def _create_verification_sync(
    database_url: str,
    telegram_id: int,
    method: str = "website",
):
    ensure_user(
        database_url,
        telegram_id,
    )

    pool = get_pool(database_url)

    with pool.connection() as conn:
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
            SET
                is_verified = TRUE,
                access_expires_at = %s,
                updated_at = NOW()
            WHERE id = %s
            """,
            (
                expires_at,
                user_id,
            ),
        )

        conn.execute(
            """
            INSERT INTO verifications (
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

        conn.commit()

        return expires_at


def create_verification(
    database_url: str,
    telegram_id: int,
    method: str = "website",
):
    return _create_verification_sync(
        database_url,
        telegram_id,
        method,
    )


async def create_verification_async(
    database_url: str,
    telegram_id: int,
    method: str = "website",
):
    return await asyncio.to_thread(
        _create_verification_sync,
        database_url,
        telegram_id,
        method,
    )


def _has_valid_access_sync(
    database_url: str,
    telegram_id: int,
) -> bool:
    pool = get_pool(database_url)

    with pool.connection() as conn:
        row = conn.execute(
            """
            SELECT
                is_verified,
                access_expires_at
            FROM users
            WHERE telegram_id = %s
            """,
            (telegram_id,),
        ).fetchone()

        if row is None:
            return False

        is_verified, expires_at = row

        if not is_verified:
            return False

        if expires_at is None:
            return False

        return expires_at > datetime.now(timezone.utc)


def has_valid_access(
    database_url: str,
    telegram_id: int,
) -> bool:
    return _has_valid_access_sync(
        database_url,
        telegram_id,
    )


async def has_valid_access_async(
    database_url: str,
    telegram_id: int,
) -> bool:
    return await asyncio.to_thread(
        _has_valid_access_sync,
        database_url,
        telegram_id,
    )