import os
import asyncio
from datetime import datetime, timezone

import psycopg
from dotenv import load_dotenv
from telethon import TelegramClient, events, Button


load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")


bot = TelegramClient("bot_session", API_ID, API_HASH)


def get_access_status(telegram_id):
    with psycopg.connect(DATABASE_URL) as conn:
        row = conn.execute(
            """
            SELECT is_verified, access_expires_at
            FROM users
            WHERE telegram_id = %s
            """,
            (telegram_id,),
        ).fetchone()

    if row is None:
        return False, None

    is_verified, expires_at = row

    if not is_verified or expires_at is None:
        return False, None

    if expires_at <= datetime.now(timezone.utc):
        return False, expires_at

    return True, expires_at


@bot.on(events.NewMessage(pattern=r"^/start$"))
async def start_handler(event):
    user = await event.get_sender()

    valid, expires_at = get_access_status(user.id)

    if valid:
        await event.respond(
            "✅ Access Active\n\n"
            "Your verification is currently active."
        )
    else:
        await event.respond(
            "🔐 Verification Required\n\n"
            "Your access is not currently active."
        )


@bot.on(events.NewMessage())
async def search_handler(event):
    text = event.raw_text.strip()

    if not text or text.startswith("/"):
        return

    with psycopg.connect(DATABASE_URL) as conn:
        rows = conn.execute(
            """
            SELECT id, title, language, quality, duration_seconds
            FROM videos
            WHERE title ILIKE %s
            ORDER BY title
            LIMIT 10
            """,
            (f"%{text}%",),
        ).fetchall()

    if not rows:
        await event.respond(
            "❌ Koi matching content nahi mila."
        )
        return

    message = "🔎 Search Results\n\n"
    buttons = []

    for i, row in enumerate(rows, start=1):
        video_id, title, language, quality, duration = row

        message += f"{i}. {title}\n"

        if language:
            message += f"🌐 {language}"

        if quality:
            message += f" • 🎞 {quality}"

        if duration:
            minutes = duration // 60
            message += f" • ⏱ {minutes} min"

        message += "\n\n"

        buttons.append(
            [
                Button.inline(
                    f"🎬 {title}",
                    data=f"video_{video_id}"
                )
            ]
        )

    await event.respond(
        message,
        buttons=buttons
    )


@bot.on(events.CallbackQuery(pattern=b"video_"))
async def video_button_handler(event):
    video_id = int(event.data.decode().split("_")[1])

    with psycopg.connect(DATABASE_URL) as conn:
        row = conn.execute(
            """
            SELECT title, language, quality, duration_seconds
            FROM videos
            WHERE id = %s
            """,
            (video_id,),
        ).fetchone()

    if row is None:
        await event.answer(
            "Content nahi mila.",
            alert=True
        )
        return

    title, language, quality, duration = row

    message = f"🎬 {title}\n\n"

    if language:
        message += f"🌐 Language: {language}\n"

    if quality:
        message += f"🎞 Quality: {quality}\n"

    if duration:
        minutes = duration // 60
        message += f"⏱ Duration: {minutes} min\n"

    message += "\n✅ Content selected."

    await event.answer()
    await event.respond(message)


async def main():
    await bot.start(bot_token=BOT_TOKEN)

    print("BOT IS ONLINE")

    await bot.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())