import os
from dataclasses import dataclass
from urllib.parse import quote

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    bot_token: str = os.getenv("BOT_TOKEN", "")
    admin_chat_id: str = os.getenv("ADMIN_CHAT_ID", "")

    # PostgreSQL — либо готовый DATABASE_URL, либо компоненты (Amvera отдаёт по частям).
    database_url: str = os.getenv("DATABASE_URL", "")
    database_host: str = os.getenv("DATABASE_HOST", "")
    database_port: str = os.getenv("DATABASE_PORT", "5432")
    database_user: str = os.getenv("DATABASE_USER", "")
    database_password: str = os.getenv("DATABASE_PASSWORD", "")
    database_name: str = os.getenv("DATABASE_NAME", "")

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

    # Веб-дашборд (этап 8). DASHBOARD_PASSWORD — секрет, только ENV.
    dashboard_user: str = os.getenv("DASHBOARD_USER", "")
    dashboard_password: str = os.getenv("DASHBOARD_PASSWORD", "")
    web_port: int = int(os.getenv("WEB_PORT") or os.getenv("PORT") or "8080")

    # AI-фолбэк (этап 6)
    ai_daily_limit: int = int(os.getenv("AI_DAILY_LIMIT") or "20")

    # Сквозная аналитика (этап 7)
    ga4_measurement_id: str = os.getenv("GA4_MEASUREMENT_ID", "G-6XY6XFGE6H")
    ga4_api_secret: str = os.getenv("GA4_API_SECRET", "")
    ym_counter_id: str = os.getenv("YM_COUNTER_ID", "110157768")
    ym_oauth_token: str = os.getenv("YM_OAUTH_TOKEN", "")
    ym_upload_interval: int = int(os.getenv("YM_UPLOAD_INTERVAL") or "1800")
    site_origin: str = os.getenv("SITE_ORIGIN", "https://russianlineup.ru")

    @property
    def dsn(self) -> str:
        """DSN для asyncpg.

        Amvera отдаёт JDBC-URL (`jdbc:postgresql://host:port/db`) без логина/пароля, а
        креды — отдельными переменными. Поэтому: снимаем префикс `jdbc:`, и если в URL
        нет кредов (`@`) — вживляем `DATABASE_USER`/`DATABASE_PASSWORD`. Если URL пуст —
        собираем из компонентов `DATABASE_HOST/PORT/USER/PASSWORD/NAME`.
        """
        password = quote(self.database_password, safe="")
        url = self.database_url
        if url.startswith("jdbc:"):
            url = url[len("jdbc:"):]
        if url:
            if "@" not in url and self.database_user and "://" in url:
                scheme, _, rest = url.partition("://")
                return f"{scheme}://{self.database_user}:{password}@{rest}"
            return url
        if self.database_host and self.database_user:
            name = self.database_name or self.database_user
            return (
                f"postgresql://{self.database_user}:{password}"
                f"@{self.database_host}:{self.database_port}/{name}"
            )
        return ""


settings = Settings()
