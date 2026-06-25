"""Тексты и клавиатуры FAQ (этап 3).

Цены/условия НЕ хардкодим — они приходят из ENV через settings.
Публичные ссылки на сообщества репозиторий публичный, поэтому держим их здесь.
"""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.config import Settings

# Публичные ссылки на сообщества (можно держать в коде — они публичные)
TG_COMMUNITIES = (
    "t.me/russian_lineup_misovoe",
    "t.me/surf_arugambay",
    "t.me/surflanka_ug",
    "t.me/fedrbodr_start_up",
)
INSTAGRAM = "instagram.com/fedrbodr"
LINKEDIN = "linkedin.com/in/dmitry-fedorenko"
MANAGER = "@sportdoski"


def boards_text(settings: Settings) -> str:
    """FAQ по доскам/электросёрфу. Цены подставляются из ENV."""
    return (
        "Электросёрф — это просто: ~90% новичков встают уже на первом занятии. "
        "Полная свобода и автономность — не нужен катер или вейк-парк, доска "
        "убирается в багажник, разгон до 55 км/ч. Подберём модель под твой вес и "
        "задачи, оборудование от производителя с гарантией.\n\n"
        f"Модели: 12 кВт — {settings.board_12kw} (райдер ~100 кг), "
        f"14 кВт — {settings.board_14kw} (до 130 кг).\n"
        f"Допы: комплект с сиденьем — {settings.seat_kit}, доп. батарея — "
        f"{settings.battery_1} (50–70 мин) / {settings.battery_2} (60–80 мин).\n"
        f"Предзаказ: {settings.preorder_terms}."
    )


def camps_text(settings: Settings) -> str:
    """FAQ по зимним кампам."""
    return (
        "Зимой уходим на тепло — Шри-Ланка 🌴 Обычный сёрфинг + электросёрф, "
        "возможен сёрф-коливинг на вилле. Даты и детали анонсируем — "
        "следи за каналами 👇"
    )


def community_text(settings: Settings) -> str:
    """Публичные ссылки на наши сообщества."""
    return (
        "Подписывайся и следи за нами 👇\n"
        f"🏄 TG-сообщества: {' · '.join(TG_COMMUNITIES)}\n"
        f"📸 Instagram: {INSTAGRAM}\n"
        f"💼 LinkedIn: {LINKEDIN}\n"
        f"💬 Менеджер: {MANAGER}"
    )


def boards_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🌊 Тест-день", callback_data="lead:testday")],
            [InlineKeyboardButton(text="📝 Оставить заявку", callback_data="lead:preorder")],
            [InlineKeyboardButton(text="🎟 Промокод", callback_data="promo:get")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:main")],
        ]
    )


def camps_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔗 Наши комьюнити", callback_data="faq:community")],
            [InlineKeyboardButton(text="📝 Оставить заявку", callback_data="lead:testday")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:main")],
        ]
    )


def community_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📝 Оставить заявку", callback_data="lead:testday")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:main")],
        ]
    )
