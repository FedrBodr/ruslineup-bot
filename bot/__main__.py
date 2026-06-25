import asyncio
import logging

from aiogram import Bot, Dispatcher

from bot.config import settings
from bot.handlers import start


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN is empty — fill .env / Amvera variables")

    bot = Bot(token=settings.bot_token)
    dp = Dispatcher()
    dp.include_router(start.router)

    logging.getLogger("bot").info("Bot started (polling)")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
