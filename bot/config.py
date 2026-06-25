import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    bot_token: str = os.getenv("BOT_TOKEN", "")
    admin_chat_id: str = os.getenv("ADMIN_CHAT_ID", "")
    sheet_id: str = os.getenv("SHEET_ID", "")
    google_sa_json: str = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "service_account.json")
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_model: str = os.getenv("LLM_MODEL", "")
    partner_nick: str = os.getenv("PARTNER_NICK", "@partner_nick")


settings = Settings()
