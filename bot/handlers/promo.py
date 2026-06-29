"""Промокоды (этап 5).

Выдаёт детерминированный промокод (один пользователь = один код), сохраняет его
один раз в таблицу `promo` и показывает контакт партнёра со скидкой.
"""
import logging
from urllib.parse import quote

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

import bot.services.db as db
import bot.services.ga4 as ga4
from bot.config import settings
from bot.services.metrics import log_event
from bot.services.promocode import generate_code

router = Router()
logger = logging.getLogger("promo")


def _promo_text(code: str) -> str:
    return (
        f"Твой код: <b>{code}</b> 🎟\n"
        f"Напиши {settings.partner_nick}, назови код — "
        f"получишь скидку {settings.partner_discount} на доску."
    )


# Заготовка сообщения менеджеру: открываем чат с уже введённым приветствием и кодом.
MANAGER_PREFILL = (
    "Привет! 🏄 Мой промокод на скидку: {code}. Хочу узнать про доски/электросёрф."
)


def _promo_kb(code: str) -> InlineKeyboardMarkup:
    nick = settings.partner_nick.lstrip("@")
    prefill = quote(MANAGER_PREFILL.format(code=code), safe="")
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="💬 Написать менеджеру",
                url=f"https://t.me/{nick}?text={prefill}",
            )],
            # menu:main реализует этап FED-240 — здесь только ссылаемся на callback_data
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:main")],
        ]
    )


@router.callback_query(F.data == "promo:get")
async def on_promo_get(callback: CallbackQuery) -> None:
    user = callback.from_user
    code = generate_code(user.id)
    await db.insert_promo(code=code, user_id=user.id, username=user.username)
    await log_event(user, event="promo_issue", detail=code)
    await callback.message.edit_text(
        _promo_text(code),
        parse_mode="HTML",
        reply_markup=_promo_kb(code),
    )
    await callback.answer()
    # Аналитика — best-effort, ПОСЛЕ ответа пользователю (сбой не ломает выдачу кода).
    try:
        cids = await db.get_user_cids(user.id)
        if cids.get("ga4_cid"):
            await ga4.send_event(cids["ga4_cid"], "promo_issue", {"code": code})
        if cids.get("ym_cid"):
            await db.enqueue_conversion(user_id=user.id, ym_cid=cids["ym_cid"], target="promo")
    except Exception:
        logger.warning("promo analytics failed (best-effort)", exc_info=True)
