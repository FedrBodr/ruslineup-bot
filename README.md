# ruslineup-bot

Telegram-бот бренда «Русский Лайнап»: приём заявок, AI-общение с клиентами (гибрид FAQ + LLM), выдача промокодов партнёра, сквозная аналитика. Полное ТЗ — `TZ_telegram_bot_v1.md` (в проекте «Русский лайнап»).

**Стек:** Python 3.11 · aiogram 3 · PostgreSQL (asyncpg) · деплой на Amvera из git.

## Запуск локально

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # вписать BOT_TOKEN и остальное
python -m bot
```

Тесты:

```bash
pip install -r requirements-dev.txt
PYTHONPATH=. pytest -q
```

Юнит-тесты мокают БД и не требуют Postgres. Интеграционный тест слоя данных —
**явный opt-in** (`RUN_DB_INTEGRATION=1`), чтобы не запускаться автоматически из-за
`DATABASE_URL` в `.env`. Гонять только против **выделенной** базы `ruslineup`:

```bash
RUN_DB_INTEGRATION=1 PYTHONPATH=. pytest tests/test_db_integration.py -v
```

## Деплой на Amvera

1. Создать приложение в Amvera (тип — **Python 3.11**), подключить этот git-репозиторий (ветку для деплоя).
2. Сборка/запуск — в `amvera.yml` (`pip` + `python -m bot`, long-polling). Persistent-диск не нужен: source of truth — внешний PostgreSQL.
3. В «Переменные и секреты» Amvera (НЕ в git) задать:
   - обязательные: `BOT_TOKEN`, `DATABASE_URL`, `ADMIN_CHAT_ID`
   - промокоды/контент: `PARTNER_NICK`, `PARTNER_DISCOUNT`, `BOARD_12KW`, `BOARD_14KW`, `SEAT_KIT`, `BATTERY_1`, `BATTERY_2`, `PREORDER_TERMS`, `TESTDAY_PRICE`
   - на этап 6 (AI): `LLM_API_KEY`, `LLM_MODEL`, `AI_DAILY_LIMIT`
4. Деплой: `git push` в Amvera-remote (или авто-сборка при push в подключённую ветку GitHub).
5. **Один инстанс** (long-polling): не запускать вторую реплику — Telegram отдаст `409 Conflict`. При старте бот сам снимает вебхук (`delete_webhook(drop_pending_updates=True)`).

### Smoke-тест в проде (чек-лист)

- [ ] `/start` → приветствие + меню; в `events` строка (event=`start`, верный `utm_source` из deep-link).
- [ ] FAQ (доски/кампы/комьюнити) → тексты с подставленными из ENV ценами; лог `faq_click`.
- [ ] Заявка (тест-день): имя→город→контакт→коммент → строка в `leads` + уведомление в `ADMIN_CHAT_ID`; лог `lead_submit`.
- [ ] Промокод → `RL-XXXX` + ник/скидка из ENV; повтор даёт тот же код; строка в `promo`; лог `promo_issue`.
- [ ] Логи Amvera без ошибок; БД поднялась (схема создалась).

## Структура

```
bot/
├── __main__.py        точка входа (polling) + init пула
├── config.py          чтение ENV
├── keyboards.py       главное меню
├── handlers/          start · faq · lead · promo (готовы), ai — этап 6
├── services/          db · metrics · promocode (готовы), llm — этап 6
└── content/           тексты FAQ (faq.py), база знаний AI — этап 6
tests/                 юнит-тесты (мок БД) + gated интеграционный
```

Хранилище — **PostgreSQL** (asyncpg): таблицы `events`, `users`, `leads`, `promo`
(+ `tokens` на этапе 7). `DATABASE_URL` — только через ENV/секреты Amvera.

## Дашборд (этап 8)

Две точки доступа к аналитике:

- **`/stats` в боте** — команда **только для админа** (`from_user.id == ADMIN_CHAT_ID`): воронка (старты/источники/заявки/промокоды + конверсии) текстом в чат.
- **Веб-морда** — `bot/web.py` (aiohttp) поднимается в том же процессе на `WEB_PORT`, закрыта **Basic-auth** (`DASHBOARD_USER`/`DASHBOARD_PASSWORD`). Показывает воронку + последние заявки; **контакт маскируется** (`+7926***3341`). Без кредов веб не поднимается.

⚠️ Для веб-морды Amvera должна **отдавать HTTP-порт** на приложение (сейчас бот — worker на long-polling). Включи веб/проброс порта в Amvera и задай переменные. На `/stats` и работу бота это не влияет.

## AI-фолбэк (этап 6)

Бот отвечает на свободные текстовые сообщения через OpenAI Chat Completions (модель задаётся через ENV).

### Как работает

1. Любое текстовое сообщение вне FSM и команд (`/...`) попадает в catch-all хендлер `bot/handlers/ai.py`.
2. Хендлер проверяет дневной лимит (`AI_DAILY_LIMIT`, дефолт 20 запросов на пользователя) по таблице `events`.
3. Вызывается `bot/services/llm.py` → `ask(user_id, question)`:
   - Системный промпт составляется из `bot/content/knowledge.md` + ENV-фактов (цены, скидка, ник менеджера).
   - Сохраняется история диалога в процессе (≤ 6 реплик на пользователя).
   - OpenAI возвращает JSON `{"answer": "...", "can_answer": true|false}`.
4. Если `can_answer=false` (данных не хватает) или ключ не задан — **эскалация к менеджеру**: к ответу прикрепляется inline-кнопка «Написать менеджеру» (`PARTNER_NICK`).

### Переменные ENV

| Переменная      | Обязательна | Описание                                          |
|-----------------|-------------|---------------------------------------------------|
| `LLM_API_KEY`   | нет         | OpenAI API key (`sk-...`). Без него AI выключен   |
| `LLM_MODEL`     | нет         | Модель, дефолт `gpt-4o`                           |
| `AI_DAILY_LIMIT`| нет         | Лимит вопросов на пользователя в день, дефолт 20  |

Нет ключа → бот немедленно эскалирует к менеджеру, OpenAI не вызывается.

### База знаний (`bot/content/knowledge.md`)

Содержит общие факты о бренде (описание оборудования, тест-дней, кэмпов, комьюнити) **без цен, скидок и контактов** — конкретику `llm.py` подставляет из ENV в рантайме. Можно дополнять фактами, не трогая код.

## Безопасность (репозиторий публичный)

Секреты и чувствительные данные — только в ENV / переменных Amvera, не в коде. Цены, условия предзаказа, размер скидки партнёра и контакты подставляются из переменных (`BOARD_12KW`, `BOARD_14KW`, `SEAT_KIT`, `BATTERY_1`, `BATTERY_2`, `PREORDER_TERMS`, `TESTDAY_PRICE`, `PARTNER_DISCOUNT`, `PARTNER_NICK`). Тексты FAQ и `knowledge.md` держим обобщёнными.

## Статус

Готовы **этапы 1–5**: каркас + `/start`, метрики в PostgreSQL (`events`/`users`), FAQ-кнопки, заявки (FSM → `leads`), промокоды (`promo`). Этап 9 — деплой на Amvera. Этапы 6–8 (AI, сквозная аналитика, дашборд) — см. `docs/CLAUDE_CODE_TASKS.md`.
