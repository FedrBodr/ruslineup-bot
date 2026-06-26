from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu() -> InlineKeyboardMarkup:
    """Главное меню бота (этап 1). callback_data разбираются на этапах 3-6."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏄 Доски / электросёрф", callback_data="faq:boards")],
            [InlineKeyboardButton(text="🌊 Тест-день (запись)", callback_data="lead:testday")],
            [InlineKeyboardButton(text="❄️ Зимние кэмпы", callback_data="faq:camps")],
            [InlineKeyboardButton(text="🎟 Промокод на скидку", callback_data="promo:get")],
            [InlineKeyboardButton(text="💬 Задать вопрос", callback_data="ai:ask")],
            [InlineKeyboardButton(text="🔗 Наши комьюнити", callback_data="faq:community")],
        ]
    )
