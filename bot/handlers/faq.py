"""FAQ-кнопки (этап 3): доски, кампы, комьюнити + возврат в главное меню."""
from aiogram import F, Router
from aiogram.types import CallbackQuery

from bot.config import settings
from bot.content.faq import (
    boards_kb,
    boards_text,
    camps_kb,
    camps_text,
    community_kb,
    community_text,
)
from bot.keyboards import main_menu
from bot.services.metrics import log_event

router = Router()

MENU_GREETING = "Главное меню 🏄 Выбери, что интересно, или задай вопрос — отвечу."


@router.callback_query(F.data == "faq:boards")
async def on_boards(callback: CallbackQuery) -> None:
    await log_event(callback.from_user, event="faq_click", detail="boards")
    await callback.message.edit_text(boards_text(settings), reply_markup=boards_kb())
    await callback.answer()


@router.callback_query(F.data == "faq:camps")
async def on_camps(callback: CallbackQuery) -> None:
    await log_event(callback.from_user, event="faq_click", detail="camps")
    await callback.message.edit_text(camps_text(settings), reply_markup=camps_kb())
    await callback.answer()


@router.callback_query(F.data == "faq:community")
async def on_community(callback: CallbackQuery) -> None:
    await log_event(callback.from_user, event="faq_click", detail="community")
    await callback.message.edit_text(
        community_text(settings), reply_markup=community_kb()
    )
    await callback.answer()


@router.callback_query(F.data == "menu:main")
async def on_menu_main(callback: CallbackQuery) -> None:
    await callback.message.edit_text(MENU_GREETING, reply_markup=main_menu())
    await callback.answer()
