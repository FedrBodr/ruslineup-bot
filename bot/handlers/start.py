from aiogram import Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import Message

import bot.services.db as db
from bot.keyboards import main_menu
from bot.services.metrics import log_event

router = Router()

WELCOME = (
    "Привет! Это бот «Русский Лайнап» 🏄\n\n"
    "Электросёрф, тест-дни и зимние кампы. "
    "Выбери, что интересно, или задай вопрос — отвечу."
)


@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject) -> None:
    user = message.from_user
    # deep-link параметр t.me/bot?start=<utm> → источник трафика; "direct" если пусто
    utm = command.args or "direct"
    # Сохраняем источник пользователя (first-touch), чтобы атрибутировать дальнейшие события.
    await db.upsert_user_utm(user_id=user.id, username=user.username, utm_source=utm)
    await log_event(user, event="start", detail="", utm=utm)
    await message.answer(WELCOME, reply_markup=main_menu())
