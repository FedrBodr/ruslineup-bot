import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    bot_token: str = os.getenv("BOT_TOKEN", "")
    admin_chat_id: str = os.getenv("ADMIN_CHAT_ID", "")
    database_url: str = os.getenv("DATABASE_URL", "")
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_model: str = os.getenv("LLM_MODEL", "")

    # Промокоды (этап 5)
    partner_nick: str = os.getenv("PARTNER_NICK", "@partner_nick")
    partner_discount: str = os.getenv("PARTNER_DISCOUNT", "")

    # Доски / электросёрф (этап 3 — FAQ). Чувствительные значения только из ENV.
    board_12kw: str = os.getenv("BOARD_12KW", "")
    board_14kw: str = os.getenv("BOARD_14KW", "")
    seat_kit: str = os.getenv("SEAT_KIT", "")
    battery_1: str = os.getenv("BATTERY_1", "")
    battery_2: str = os.getenv("BATTERY_2", "")
    preorder_terms: str = os.getenv("PREORDER_TERMS", "")

    # Тест-день (этап 4). В v1 фикс. цены нет — бот говорит «уточняйте у менеджера».
    testday_price: str = os.getenv("TESTDAY_PRICE", "")


settings = Settings()
