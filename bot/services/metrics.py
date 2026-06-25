"""Единая точка логирования событий. Пишет в Postgres (таблица `events`) + в лог.

`log_event` — best-effort: сбой БД не должен ломать пользовательский флоу,
поэтому запись обёрнута в try/except. utm_source приходит только на `/start`;
для остальных событий он подтягивается из таблицы `users`.
"""
import logging
from typing import Optional

import bot.services.db as db

logger = logging.getLogger("metrics")


async def log_event(user, event: str, detail: str = "", utm: Optional[str] = None) -> None:
    # На /start utm передаётся явно; иначе берём сохранённый источник пользователя.
    try:
        source = utm if utm is not None else await db.get_user_utm(user.id)
    except Exception:
        source = utm
    source = source or ""

    logger.info(
        "event=%s user_id=%s username=%s detail=%r utm=%s",
        event,
        user.id,
        user.username,
        detail,
        source,
    )

    try:
        await db.append_event(
            user_id=user.id,
            username=user.username,
            utm_source=source,
            event=event,
            detail=detail,
        )
    except Exception:
        logger.warning(
            "append_event failed for event=%s user_id=%s (metrics best-effort)",
            event,
            user.id,
            exc_info=True,
        )
