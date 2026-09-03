import os
import asyncio
import re

import psycopg
from dotenv import load_dotenv
from telethon import TelegramClient, events, Button
from telethon.tl.types import DocumentAttributeVideo

from backend.verification import (
    create_verification_token,
    ensure_user_async,
    has_valid_access_async,
)

load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

DATABASE_URL = os.getenv("DATABASE_URL")
VERIFICATION_SECRET = os.getenv("VERIFICATION_SECRET")
WEBSITE_URL = os.getenv("WEBSITE_URL")

BOT_USERNAME = os.getenv(
    "BOT_USERNAME",
    "freemoviesHD28_bot",
)

SOURCE_CHAT_ID = os.getenv("SOURCE_CHAT_ID")

if not SOURCE_CHAT_ID:
    raise RuntimeError(
        "SOURCE_CHAT_ID is not configured"
    )

SOURCE_CHAT_ID = int(SOURCE_CHAT_ID)

bot = TelegramClient(
    "bot_session",
    API_ID,
    API_HASH,
)


# ==================================================
# DATABASE
# ==================================================

def get_video(video_id: int):
    with psycopg.connect(DATABASE_URL) as conn:
        return conn.execute(
            """
            SELECT
                id,
                title,
                language,
                quality,
                file_size_bytes,
                duration_seconds,
                source_chat_id,
                source_message_id
            FROM videos
            WHERE id = %s
              AND is_active = TRUE
            """,
            (video_id,),
        ).fetchone()


def search_videos(text: str):
    with psycopg.connect(DATABASE_URL) as conn:
        return conn.execute(
            """
            SELECT
                id,
                title,
                language,
                quality,
                file_size_bytes,
                duration_seconds
            FROM videos
            WHERE title ILIKE %s
              AND is_active = TRUE
            ORDER BY
                title,
                language,
                quality
            LIMIT 30
            """,
            (f"%{text}%",),
        ).fetchall()


def video_exists(
    source_chat_id: int,
    source_message_id: int,
):
    with psycopg.connect(DATABASE_URL) as conn:
        row = conn.execute(
            """
            SELECT id
            FROM videos
            WHERE source_chat_id = %s
              AND source_message_id = %s
            LIMIT 1
            """,
            (
                source_chat_id,
                source_message_id,
            ),
        ).fetchone()

        return row is not None


# ==================================================
# METADATA PARSER
# ==================================================

LANGUAGE_PATTERNS = [
    "Hindi",
    "English",
    "Tamil",
    "Telugu",
    "Malayalam",
    "Kannada",
    "Bengali",
    "Marathi",
    "Punjabi",
    "Gujarati",
    "Odia",
    "Assamese",
    "Dual Audio",
    "Multi Audio",
]

QUALITY_PATTERNS = [
    "2160p",
    "1080p",
    "720p",
    "480p",
    "360p",
    "144p",
    "4K",
]


def clean_text(value):
    if not value:
        return ""

    value = value.replace("\n", " ")
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def parse_metadata_from_text(text):
    text = clean_text(text)

    language = None
    quality = None

    # -------------------------------
    # Language
    # -------------------------------

    for item in LANGUAGE_PATTERNS:
        pattern = rf"(?<!\w){re.escape(item)}(?!\w)"

        if re.search(
            pattern,
            text,
            re.IGNORECASE,
        ):
            language = item
            break

    # -------------------------------
    # Quality
    # -------------------------------

    for item in QUALITY_PATTERNS:
        pattern = rf"(?<!\w){re.escape(item)}(?!\w)"

        if re.search(
            pattern,
            text,
            re.IGNORECASE,
        ):
            quality = item
            break

    return language, quality


def extract_video_metadata(message):

    caption = clean_text(
        message.raw_text
        if message.raw_text
        else ""
    )

    file_name = None
    file_size = None
    duration = None

    if message.file:

        file_name = getattr(
            message.file,
            "name",
            None,
        )

        file_size = getattr(
            message.file,
            "size",
            None,
        )

    document = getattr(
        message,
        "document",
        None,
    )

    if document:

        attributes = (
            getattr(
                document,
                "attributes",
                None,
            )
            or []
        )

        for attribute in attributes:

            if isinstance(
                attribute,
                DocumentAttributeVideo,
            ):
                duration = attribute.duration
                break

            if (
                getattr(
                    attribute,
                    "file_name",
                    None,
                )
                and not file_name
            ):
                file_name = attribute.file_name

    file_name = clean_text(file_name)

    # -----------------------------------------
    # Preferred format:
    #
    # Movie Name | Hindi | 720p
    # -----------------------------------------

    title = None
    language = None
    quality = None

    if caption:

        parts = [
            clean_text(part)
            for part in caption.split("|")
        ]

        parts = [
            part
            for part in parts
            if part
        ]

        if parts:
            title = parts[0]

        remaining_text = " ".join(
            parts[1:]
        )

        language, quality = (
            parse_metadata_from_text(
                remaining_text
            )
        )

        # Also detect metadata from full caption
        if not language:
            language, _ = (
                parse_metadata_from_text(
                    caption
                )
            )

        if not quality:
            _, quality = (
                parse_metadata_from_text(
                    caption
                )
            )

    # -----------------------------------------
    # Fallback: filename
    # -----------------------------------------

    if not title and file_name:

        title = file_name

        detected_language, detected_quality = (
            parse_metadata_from_text(
                file_name
            )
        )

        if not language:
            language = detected_language

        if not quality:
            quality = detected_quality

    # -----------------------------------------
    # Final fallback
    # -----------------------------------------

    if not title:
        title = "Untitled Video"

    return {
        "title": title,
        "language": language,
        "quality": quality,
        "file_size_bytes": file_size,
        "duration_seconds": duration,
        "file_name": file_name or None,
    }


# ==================================================
# AUTO REGISTER VIDEO
# ==================================================

def register_video_from_message(message):

    source_chat_id = SOURCE_CHAT_ID
    source_message_id = message.id

    if video_exists(
        source_chat_id,
        source_message_id,
    ):
        print(
            "VIDEO ALREADY REGISTERED:",
            source_message_id,
        )
        return None

    metadata = extract_video_metadata(
        message
    )

    with psycopg.connect(DATABASE_URL) as conn:

        row = conn.execute(
            """
            INSERT INTO videos (
                title,
                language,
                quality,
                file_size_bytes,
                duration_seconds,
                source_chat_id,
                source_message_id,
                file_name,
                is_active
            )
            VALUES (
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                TRUE
            )
            RETURNING id
            """,
            (
                metadata["title"],
                metadata["language"],
                metadata["quality"],
                metadata["file_size_bytes"],
                metadata["duration_seconds"],
                source_chat_id,
                source_message_id,
                metadata["file_name"],
            ),
        ).fetchone()

        conn.commit()

    video_id = row[0]

    print(
        "VIDEO REGISTERED:",
        video_id,
    )

    print(
        "TITLE:",
        metadata["title"],
    )

    print(
        "LANGUAGE:",
        metadata["language"],
    )

    print(
        "QUALITY:",
        metadata["quality"],
    )

    print(
        "SIZE:",
        metadata["file_size_bytes"],
    )

    print(
        "DURATION:",
        metadata["duration_seconds"],
    )

    print(
        "MESSAGE ID:",
        source_message_id,
    )

    return video_id


# ==================================================
# STORAGE CHANNEL HANDLER
# ==================================================

@bot.on(
    events.NewMessage(
        incoming=True,
        chats=SOURCE_CHAT_ID,
    )
)
async def storage_handler(event):

    if event.out:
        return

    message = event.message

    if not message:
        return

    if not message.file:
        return

    mime_type = (
        getattr(
            message.file,
            "mime_type",
            None,
        )
        or ""
    ).lower()

    if not mime_type.startswith("video/"):
        return

    try:

        video_id = await asyncio.to_thread(
            register_video_from_message,
            message,
        )

        if video_id:

            print(
                "AUTO REGISTRATION SUCCESS:",
                video_id,
            )

    except Exception as exc:

        print(
            "AUTO REGISTRATION ERROR:",
            repr(exc),
        )


# ==================================================
# START / VIDEO DELIVERY
# ==================================================

@bot.on(
    events.NewMessage(
        incoming=True,
        pattern=r"^/start(?:@\w+)?(?:\s+(.+))?$",
    )
)
async def start_handler(event):

    if event.out:
        return

    user = await event.get_sender()

    if user is None:
        return

    await ensure_user_async(
        DATABASE_URL,
        user.id,
        getattr(
            user,
            "username",
            None,
        ),
        getattr(
            user,
            "first_name",
            None,
        ),
    )

    start_parameter = None

    if event.pattern_match:

        start_parameter = (
            event.pattern_match.group(1)
        )

    selected_video = None

    if (
        start_parameter
        and start_parameter.startswith(
            "video_"
        )
    ):

        try:

            video_id = int(
                start_parameter.split(
                    "_",
                    1,
                )[1]
            )

        except (
            ValueError,
            IndexError,
        ):
            video_id = None

        if video_id is not None:

            selected_video = (
                await asyncio.to_thread(
                    get_video,
                    video_id,
                )
            )

    valid = await has_valid_access_async(
        DATABASE_URL,
        user.id,
    )

    # ==========================================
    # SELECTED VIDEO + VERIFIED
    # ==========================================

    if selected_video and valid:

        (
            video_id,
            title,
            language,
            quality,
            size_bytes,
            duration,
            source_chat_id,
            source_message_id,
        ) = selected_video

        if (
            not source_chat_id
            or not source_message_id
        ):

            await event.respond(
                "⚠️ This video is not connected "
                "to storage yet."
            )

            return

        try:

            source_message = (
                await bot.get_messages(
                    source_chat_id,
                    ids=source_message_id,
                )
            )

            if not source_message:

                await event.respond(
                    "❌ Video could not be found "
                    "in Video Storage."
                )

                return

            await event.respond(
                "✅ Verification Active\n\n"
                f"🎬 {title}\n"
                "📤 Sending your selected video..."
            )

            await bot.forward_messages(
                event.chat_id,
                source_message,
                from_peer=source_chat_id,
            )

        except Exception as exc:

            print(
                "VIDEO DELIVERY ERROR:",
                repr(exc),
            )

            await event.respond(
                "❌ Video delivery failed.\n\n"
                "Please try again."
            )

        return

    # ==========================================
    # SELECTED VIDEO + NOT VERIFIED
    # ==========================================

    if selected_video:

        (
            video_id,
            title,
            language,
            quality,
            size_bytes,
            duration,
            source_chat_id,
            source_message_id,
        ) = selected_video

        if not VERIFICATION_SECRET:

            await event.respond(
                "⚠️ Verification system is not configured."
            )

            return

        if not WEBSITE_URL:

            await event.respond(
                "⚠️ Verification website is not configured."
            )

            return

        token = create_verification_token(
            user.id,
            VERIFICATION_SECRET,
        )

        verification_url = (
            f"{WEBSITE_URL.rstrip('/')}"
            f"?token={token}"
            f"&video_id={video_id}"
        )

        await event.respond(
            f"🎬 {title}\n\n"
            "🔐 Verification Required\n\n"
            "Complete verification to continue.",
            buttons=[
                [
                    Button.url(
                        "✅ Verify Now",
                        verification_url,
                    )
                ]
            ],
        )

        return

    # ==========================================
    # NORMAL START + VERIFIED
    # ==========================================

    if valid:

        await event.respond(
            "✅ Access Active\n\n"
            "Your verification is currently active."
        )

        return

    # ==========================================
    # NORMAL START + NOT VERIFIED
    # ==========================================

    if not VERIFICATION_SECRET:

        await event.respond(
            "⚠️ Verification system is not configured."
        )

        return

    if not WEBSITE_URL:

        await event.respond(
            "⚠️ Verification website is not configured."
        )

        return

    token = create_verification_token(
        user.id,
        VERIFICATION_SECRET,
    )

    verification_url = (
        f"{WEBSITE_URL.rstrip('/')}"
        f"?token={token}"
    )

    await event.respond(
        "🔐 Verification Required\n\n"
        "Please complete verification to continue.",
        buttons=[
            [
                Button.url(
                    "✅ Verify Now",
                    verification_url,
                )
            ]
        ],
    )


# ==================================================
# SEARCH
# ==================================================

@bot.on(
    events.NewMessage(
        incoming=True,
        pattern=r"^(?!/).{2,}$",
    )
)
async def search_handler(event):

    if event.out:
        return

    text = (
        event.raw_text or ""
    ).strip()

    if not text:
        return

    rows = await asyncio.to_thread(
        search_videos,
        text,
    )

    if not rows:

        await event.respond(
            "❌ Movie not found."
        )

        return

    movies = {}

    for row in rows:

        (
            video_id,
            title,
            language,
            quality,
            size_bytes,
            duration,
        ) = row

        key = title.strip().lower()

        if key not in movies:

            movies[key] = {
                "title": title,
                "versions": [],
            }

        movies[key]["versions"].append(
            {
                "id": video_id,
                "language": language,
                "quality": quality,
                "size": size_bytes,
                "duration": duration,
            }
        )

    message = (
        "🔎 Search Results\n\n"
        f"Results for: {text}\n\n"
    )

    buttons = []

    for movie in movies.values():

        title = movie["title"]

        message += (
            f"🎬 {title}\n"
        )

        for version in movie[
            "versions"
        ]:

            details = []

            if version["language"]:

                details.append(
                    version["language"]
                )

            if version["quality"]:

                details.append(
                    version["quality"]
                )

            size = format_size(
                version["size"]
            )

            if size:
                details.append(size)

            duration = format_duration(
                version["duration"]
            )

            if duration:
                details.append(duration)

            if details:

                message += (
                    "   • "
                    + " • ".join(details)
                    + "\n"
                )

            button_text = "🎬 "

            if version["language"]:

                button_text += (
                    version["language"]
                )

            if version["quality"]:

                if version["language"]:
                    button_text += " • "

                button_text += (
                    version["quality"]
                )

            if size:

                if (
                    version["language"]
                    or version["quality"]
                ):
                    button_text += " • "

                button_text += size

            if button_text == "🎬 ":

                button_text += title

            buttons.append(
                [
                    Button.url(
                        button_text,
                        (
                            f"https://t.me/"
                            f"{BOT_USERNAME}"
                            f"?start=video_"
                            f"{version['id']}"
                        ),
                    )
                ]
            )

        message += "\n"

    await event.respond(
        message,
        buttons=buttons,
    )


# ==================================================
# FORMATTING
# ==================================================

def format_size(size_bytes):

    if not size_bytes:
        return ""

    size = float(size_bytes)

    if size >= 1024 ** 3:

        return (
            f"{size / (1024 ** 3):.2f} GB"
        )

    if size >= 1024 ** 2:

        return (
            f"{size / (1024 ** 2):.0f} MB"
        )

    if size >= 1024:

        return (
            f"{size / 1024:.0f} KB"
        )

    return f"{int(size)} B"


def format_duration(seconds):

    if not seconds:
        return ""

    seconds = int(seconds)

    hours = seconds // 3600

    minutes = (
        (seconds % 3600) // 60
    )

    if hours:

        return (
            f"{hours}h {minutes}m"
        )

    return f"{minutes}m"


# ==================================================
# MAIN
# ==================================================

async def main():

    await bot.start(
        bot_token=BOT_TOKEN,
    )

    print("BOT IS ONLINE")

    await bot.run_until_disconnected()


if __name__ == "__main__":

    asyncio.run(main())