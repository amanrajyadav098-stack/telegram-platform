import asyncio
import os

import uvicorn
from dotenv import load_dotenv

from backend.main import app
from bots.bot import bot

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")


async def main():

    await bot.start(
        bot_token=BOT_TOKEN
    )

    print("BOT IS ONLINE")

    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="0.0.0.0",
            port=int(
                os.getenv("PORT", "8000")
            ),
        )
    )

    await asyncio.gather(
        server.serve(),
        bot.run_until_disconnected(),
    )


if __name__ == "__main__":
    asyncio.run(main())