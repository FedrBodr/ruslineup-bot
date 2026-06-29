import asyncio
import logging

from aiogram import Bot, Dispatcher

from aiohttp import web as aioweb

import bot.services.db as db
import bot.services.metrika as metrika
from bot import web as dashboard
from bot.config import settings
from bot.handlers import ai, faq, lead, promo, start, stats


async def _metrika_uploader() -> None:
    while True:
        await asyncio.sleep(settings.ym_upload_interval)
        try:
            n = await metrika.upload_pending()
            if n:
                logging.getLogger("metrika").info("Uploaded %s conversions to Metrika", n)
        except Exception:
            logging.getLogger("metrika").warning("uploader tick failed", exc_info=True)


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    log = logging.getLogger("bot")

    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN is empty — fill .env / Amvera variables")

    dsn = settings.dsn
    if dsn:
        await db.init_pool(dsn)
        log.info("Postgres pool initialised; schema ensured")
    else:
        log.warning(
            "DATABASE_URL/компоненты не заданы — работаем без БД; события только в лог"
        )

    bot = Bot(token=settings.bot_token)
    dp = Dispatcher()
    dp.include_router(start.router)
    dp.include_router(faq.router)
    dp.include_router(lead.router)
    dp.include_router(promo.router)
    dp.include_router(stats.router)
    dp.include_router(ai.router)

    # Веб-дашборд рядом с поллингом — только если заданы креды Basic-auth.
    runner = None
    if settings.dashboard_user and settings.dashboard_password:
        runner = aioweb.AppRunner(dashboard.build_app())
        await runner.setup()
        await aioweb.TCPSite(runner, host="0.0.0.0", port=settings.web_port).start()
        log.info("Web dashboard on :%s", settings.web_port)
    else:
        log.warning("DASHBOARD_USER/PASSWORD не заданы — веб-дашборд выключен")

    uploader = None
    if settings.ym_oauth_token and settings.ym_counter_id:
        uploader = asyncio.create_task(_metrika_uploader())
        log.info("Metrika uploader started (interval %ss)", settings.ym_upload_interval)

    # Снимаем возможный вебхук и сбрасываем накопившийся бэклог — иначе при
    # рестарте на Amvera long-polling может словить 409 Conflict.
    await bot.delete_webhook(drop_pending_updates=True)

    log.info("Bot started (polling)")
    try:
        await dp.start_polling(bot)
    finally:
        if uploader is not None:
            uploader.cancel()
        if runner is not None:
            await runner.cleanup()
        await db.close_pool()


if __name__ == "__main__":
    asyncio.run(main())
