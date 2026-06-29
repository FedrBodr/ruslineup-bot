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
    args = command.args or ""
    utm, ga4_cid, ym_cid = "direct", None, None
    if args.startswith("tok_"):
        tok = await db.get_token(args[len("tok_"):])
        if tok:
            utm = tok.get("utm_source") or "direct"
            ga4_cid = tok.get("ga4_cid")
            ym_cid = tok.get("ym_cid")
            await db.link_token_user(token=args[len("tok_"):], user_id=user.id)
    elif "__" in args:
        src, _, cid = args.partition("__")
        utm = src or "direct"
        ym_cid = cid or None
    elif args:
        utm = args
    await db.upsert_user_utm(user_id=user.id, username=user.username, utm_source=utm)
    await db.set_user_cids(user_id=user.id, ga4_cid=ga4_cid, ym_cid=ym_cid)
    await log_event(user, event="start", detail="", utm=utm)
    await message.answer(WELCOME, reply_markup=main_menu())
