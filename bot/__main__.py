import asyncio
import logging

from aiogram import Bot, Dispatcher

import bot.services.db as db
from bot.config import settings
from bot.handlers import faq, lead, promo, start


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    log = logging.getLogger("bot")

    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN is empty — fill .env / Amvera variables")

    if settings.database_url:
        await db.init_pool(settings.database_url)
        log.info("Postgres pool initialised; schema ensured")
    else:
        log.warning("DATABASE_URL is empty — running without DB; events go to logs only")

    bot = Bot(token=settings.bot_token)
    dp = Dispatcher()
    dp.include_router(start.router)
    dp.include_router(faq.router)
    dp.include_router(lead.router)
    dp.include_router(promo.router)

    # Снимаем возможный вебхук и сбрасываем накопившийся бэклог — иначе при
    # рестарте на Amvera long-polling может словить 409 Conflict.
    await bot.delete_webhook(drop_pending_updates=True)

    log.info("Bot started (polling)")
    try:
        await dp.start_polling(bot)
    finally:
        await db.close_pool()


if __name__ == "__main__":
    asyncio.run(main())
