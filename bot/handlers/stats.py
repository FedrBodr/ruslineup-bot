"""Команда /stats — сводка для админа (этап 8)."""
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.config import settings
from bot.services.stats import Stats, get_stats

router = Router()


def render_text(s: Stats) -> str:
    src = ", ".join(f"{name or 'direct'}: {c}" for name, c in s.starts_by_source) or "—"
    types = ", ".join(f"{t or '—'}: {c}" for t, c in s.leads_by_type) or "—"
    return (
        "📊 Статистика\n"
        f"Старты: {s.starts_total} (сегодня {s.starts_today}, 7 дней {s.starts_7d})\n"
        f"Источники: {src}\n"
        f"Заявки: {s.leads_total} ({types}) · конверсия start→lead {s.lead_conv()}\n"
        f"Промокоды: {s.promo_total} · конверсия start→promo {s.promo_conv()}\n"
        f"Конверсии: {s.conv_total} (выгружено {s.conv_uploaded}, в очереди {s.conv_pending})"
    )


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    if str(message.from_user.id) != settings.admin_chat_id:
        return  # тихо игнорируем не-админа
    s = await get_stats()
    await message.answer(render_text(s))
