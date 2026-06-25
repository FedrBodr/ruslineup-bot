"""Логирование событий. Этап 1 — в консоль. Этап 2 — в Google Sheets (лист events)."""
import logging
from typing import Optional

from aiogram.types import User

logger = logging.getLogger("metrics")


def log_event(user: User, event: str, detail: str = "", utm: Optional[str] = None) -> None:
    """Единая точка логирования. На этапе 2 здесь же — append_row в Google Sheets."""
    logger.info(
        "event=%s user_id=%s username=%s detail=%r utm=%s",
        event,
        user.id,
        user.username,
        detail,
        utm or "",
    )
    # TODO (этап 2): sheets.append_event(timestamp, user.id, user.username, utm, event, detail)
