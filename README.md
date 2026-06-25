# ruslineup-bot

Telegram-бот бренда «Русский Лайнап»: приём заявок, AI-общение с клиентами (гибрид FAQ + LLM), выдача промокодов партнёра, сквозная аналитика. Полное ТЗ — `TZ_telegram_bot_v1.md` (в проекте «Русский лайнап»).

**Стек:** Python 3.11 · aiogram 3 · Google Sheets (gspread) · деплой на Amvera из git.

## Запуск локально

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # вписать BOT_TOKEN и остальное
python -m bot
```

Тесты:

```bash
pip install pytest
PYTHONPATH=. pytest -q
```

## Деплой на Amvera

1. Создать приложение в Amvera (тип — Python), подключить этот git-репозиторий.
2. Конфиг уже в `amvera.yml` (запуск `python -m bot`, polling).
3. Секреты задать в разделе «Переменные и секреты» Amvera (НЕ в git): `BOT_TOKEN`, `ADMIN_CHAT_ID`, `SHEET_ID`, `GOOGLE_SERVICE_ACCOUNT_JSON`, `PARTNER_NICK`, `LLM_API_KEY`, `LLM_MODEL`.
4. `git push` в Amvera-remote (или авто-сборка при push в GitHub) → сборка и запуск.

## Структура

```
bot/
├── __main__.py        точка входа (polling)
├── config.py          чтение ENV
├── keyboards.py       меню
├── handlers/          start (готов), faq/lead/promo/ai — этапы 3-6
├── services/          metrics, promocode (готовы), sheets/llm — этапы 2,6
└── content/           тексты FAQ, база знаний AI
tests/                 юнит-тесты
```

## Безопасность (репозиторий публичный)

Секреты и чувствительные данные — только в ENV / переменных Amvera, не в коде. Цены, условия предзаказа, размер скидки партнёра и контакты подставляются из переменных (`BOARD_PRICE`, `PREORDER_TERMS`, `TESTDAY_PRICE`, `PARTNER_DISCOUNT`, `PARTNER_NICK`). Тексты FAQ и `knowledge.md` держим обобщёнными.

## Статус

Готов **этап 1** (каркас + `/start` с меню) и `promocode` с тестами. Остальные этапы — см. `docs/CLAUDE_CODE_TASKS.md`.
