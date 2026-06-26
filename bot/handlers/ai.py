"""AI-фолбэк (этап 6): свободный вопрос → ответ OpenAI по базе знаний."""
from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

import bot.services.db as db
from bot.config import settings
from bot.services.llm import ask
from bot.services.metrics import log_event

router = Router()

ASK_PROMPT = "Задай вопрос — отвечу про электросёрф, тест-дни и кэмпы 🏄"
LIMIT_MSG = "На сегодня хватит вопросов 🙂 Напиши {nick} — поможем лично."
ESCALATE_NOTE = "Не уверен в ответе — напиши {nick}, подскажут точно."


def _manager_kb() -> InlineKeyboardMarkup:
    nick = settings.partner_nick.lstrip("@")
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="💬 Написать менеджеру",
                                               url=f"https://t.me/{nick}")]]
    )


@router.callback_query(F.data == "ai:ask")
async def on_ai_ask(callback: CallbackQuery) -> None:
    await callback.message.answer(ASK_PROMPT)
    await callback.answer()


@router.message(StateFilter(None), F.text)
async def on_free_text(message: Message) -> None:
    if message.text.startswith("/"):
        return  # команды обрабатывают другие роутеры
    user = message.from_user
    if await db.count_today_event(user.id, "ask_ai") >= settings.ai_daily_limit:
        await message.answer(LIMIT_MSG.format(nick=settings.partner_nick),
                             reply_markup=_manager_kb())
        return

    answer, escalated = await ask(user.id, message.text)
    if escalated:
        text = (answer + "\n\n" + ESCALATE_NOTE.format(nick=settings.partner_nick)).strip()
        await message.answer(text, reply_markup=_manager_kb())
    else:
        await message.answer(answer)

    detail = ("[escalate] " if escalated else "") + message.text[:200]
    await log_event(user, event="ask_ai", detail=detail)
