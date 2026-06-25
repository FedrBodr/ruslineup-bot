from aiogram import Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import Message

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
    # deep-link параметр t.me/bot?start=<utm> → источник трафика (этап 7)
    utm = command.args or "direct"
    log_event(message.from_user, event="start", detail=utm)
    await message.answer(WELCOME, reply_markup=main_menu())
