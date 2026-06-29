Project: ruslineup-bot
Document: design-spec

# Этап 7 — Сквозная аналитика (токены лендинг↔бот + GA4 + Метрика)

_2026-06-29 · FED-244 · ветка `fedrbodr/fed-244-etap-7-skvoznaya-analitika-tokens-ga4`_

## Цель

Связать веб-визит на лендинге с действиями в боте через короткий токен, чтобы серверные конверсии бота (старт, заявка, промокод, позже — продажа) атрибутировались к источнику трафика. GA4 — реалтайм через Measurement Protocol; Яндекс.Метрика (приоритет РФ) — оффлайн-конверсии по ClientID с авто-выгрузкой.

## Контекст (что уже есть)

- Лендинг `~/IdeaProjects/fedrbodr/russianlineup-site/index.html` (один статический файл, инлайн-JS). Живые счётчики **GA4 `G-6XY6XFGE6H`** и **Метрика `110157768`**. Обработчик `.js-bot` уже берёт **Metrika ClientID** и шлёт `start=<src>__<ymCid>`. GA4 ClientID НЕ берётся.
- Бот: aiohttp-веб уже поднят (этап 8, `bot/web.py`); Postgres-слой `bot/services/db.py`; `/start` сейчас кладёт весь `command.args` в utm.
- Деплой лендинга: reg.ru по FTP через GitHub Actions на `git push master`. Публичный домен бота: `https://ruslineup-bot-fedrbodr.amvera.io`.

## Поток данных

```
клик .js-bot → захват ga4_cid + ym_cid + utm_* → POST /api/token (бот) → {token}
→ открыть t.me/RussianLineupBot?start=tok_<token>
→ бот /start: get_token → сохранить cid/utm на пользователя → GA4 bot_start
→ заявка/промокод: GA4 lead_submit/promo_issue + enqueue Metrika-конверсии
→ фоновый аплоадер: батч-выгрузка конверсий в Метрику по ym_cid
```

Обратная совместимость: `/start` понимает `tok_<id>` (новое), `<src>__<cid>` (текущее) и голый utm.

---

## Фаза 1 — Фундамент (склейка)

**БД (`bot/services/db.py`):**
- Таблица `tokens`: `token TEXT PRIMARY KEY, ga4_cid TEXT, ym_cid TEXT, utm_source TEXT, utm_medium TEXT, utm_campaign TEXT, created_at TIMESTAMPTZ default now(), user_id BIGINT`.
- В `users` добавить колонки `ga4_cid TEXT, ym_cid TEXT` (для отправки событий после /start).
- Функции: `insert_token(*, token, ga4_cid, ym_cid, utm_source, utm_medium, utm_campaign)`; `get_token(token) -> dict|None`; `set_user_cids(*, user_id, ga4_cid, ym_cid)`; `get_user_cids(user_id) -> dict` (ga4_cid/ym_cid).

**Бот /web (`bot/web.py`):**
- `POST /api/token` — публичный (без Basic-auth). Тело JSON `{ga4_cid, ym_cid, utm_source, utm_medium, utm_campaign}` (любые поля опц.). Генерирует `token = secrets.token_hex(6)`, `insert_token`, отвечает `{"token": token}`. CORS: `Access-Control-Allow-Origin: <SITE_ORIGIN>` (ENV, дефолт `https://russianlineup.ru`), методы POST/OPTIONS, заголовок Content-Type. `OPTIONS /api/token` → 204 с CORS-заголовками.
- Basic-auth middleware пропускает без авторизации пути `/health` И `/api/token`.

**Лендинг (`index.html`, отдельный репо):**
- В обработчике `.js-bot`: добрать `gtag('get', ga4Id, 'client_id', cb)` (GA4 cid) и `utm_source/medium/campaign` из URL (Metrika cid уже есть). `fetch('https://ruslineup-bot-fedrbodr.amvera.io/api/token', {method:'POST', body: JSON})`; на ответ открыть `start=tok_<token>`. При ошибке/таймауте — текущий фолбэк `src__ymCid`.

**Бот `/start` (`bot/handlers/start.py`):**
- Если `command.args` начинается с `tok_` → `get_token(token)` → utm_source из токена, `set_user_cids`, `link_token_user`. Иначе: `<src>__<cid>` → src как utm (и ym_cid если распарсился); иначе голый utm как сейчас. `upsert_user_utm` сохраняется. Затем (фаза 2) GA4 `bot_start`.

**Тесты фазы 1:** db-функции (мок пула); `/api/token` POST→token + CORS-заголовки + OPTIONS 204 (aiohttp TestClient); парс `/start` для tok_/legacy/plain (мок get_token).

---

## Фаза 2 — GA4 (Measurement Protocol)

**`bot/services/ga4.py`:**
- `async send_event(client_id: str, name: str, params: dict | None = None) -> None` → POST на `https://www.google-analytics.com/mp/collect?measurement_id=<id>&api_secret=<secret>` телом `{"client_id": client_id, "events": [{"name": name, "params": params or {}}]}` через `aiohttp.ClientSession`. **ENV-gated:** нет `GA4_API_SECRET` или `GA4_MEASUREMENT_ID` или пустой `client_id` → no-op. Best-effort: ошибки сети логируются, не пробрасываются.
- События: `bot_start` (в `/start`, если у юзера есть ga4_cid), `lead_submit` (в `lead._finish`), `promo_issue` (в `promo.on_promo_get`). `client_id` = `ga4_cid` пользователя (из токена). Нет ga4_cid → событие не шлём.

**config/.env:** `GA4_MEASUREMENT_ID` (дефолт `G-6XY6XFGE6H`), `GA4_API_SECRET` (секрет).

**Тесты фазы 2:** `send_event` с моком `ClientSession.post` — собирает верный URL/тело; ветки no-op (нет секрета / нет client_id). Хендлеры: при наличии ga4_cid вызывается `send_event` с нужным именем (мок).

---

## Фаза 3 — Метрика (оффлайн-конверсии, авто-выгрузка)

**БД:** таблица `conversions`: `id BIGSERIAL PK, ts TIMESTAMPTZ default now(), user_id BIGINT, ym_cid TEXT, target TEXT, price NUMERIC, uploaded BOOLEAN default false`. Функции: `enqueue_conversion(*, user_id, ym_cid, target, price=None)`; `fetch_pending_conversions(limit=1000) -> list`; `mark_conversions_uploaded(ids: list[int])`.
- Enqueue на `lead_submit` (target `lead`) и `promo_issue` (target `promo`) — только если у юзера есть `ym_cid`.

**`bot/services/metrika.py`:**
- `async upload_pending() -> int` — `fetch_pending_conversions`; если пусто → 0. Строит CSV (`ClientId,Target,DateTime,Price,Currency`), POST multipart на `https://api-metrika.yandex.net/management/v1/counter/<YM_COUNTER_ID>/offline_conversions/upload?client_id_type=CLIENT_ID` с заголовком `Authorization: OAuth <YM_OAUTH_TOKEN>`. На успехе — `mark_conversions_uploaded`. **ENV-gated**: нет `YM_OAUTH_TOKEN`/`YM_COUNTER_ID` → no-op. Ошибки логируются, не пробрасываются.

**Фоновый аплоадер (`bot/__main__.py`):** если заданы YM-креды — asyncio-задача, раз в `YM_UPLOAD_INTERVAL` сек (дефолт 1800) вызывает `metrika.upload_pending()`; гасится в shutdown.

**config/.env:** `YM_COUNTER_ID` (дефолт `110157768`), `YM_OAUTH_TOKEN` (секрет), `YM_UPLOAD_INTERVAL` (дефолт 1800).

**Тесты фазы 3:** db-функции (мок пула); `upload_pending` с моком pending + моком POST — верный CSV/URL/заголовок, `mark_uploaded` вызван; ветка no-op без кредов. Enqueue вызывается из хендлеров при наличии ym_cid (мок).

---

## Безопасность

- Секреты `GA4_API_SECRET`, `YM_OAUTH_TOKEN` — только ENV/Amvera. `GA4_MEASUREMENT_ID`/`YM_COUNTER_ID` — публичные client-side значения, в ENV для гибкости.
- `/api/token` публичный, создаёт только строки токенов (низкий риск). CORS ограничен `SITE_ORIGIN`. При росте абьюза — добавить пер-IP лимит (вне v1).
- Все внешние вызовы (GA4/Метрика) best-effort: сбой не ломает пользовательский флоу бота.

## Тестирование (общее)

Реальных вызовов GA4/Метрики и реального HTTP к боту-API в юнит-тестах нет (aiohttp TestClient для своего эндпоинта; `ClientSession`/POST мокаются для исходящих). Слой БД — мок пула (как `tests/test_db.py`).

## Зависимости от владельца

- `GA4_API_SECRET` (GA4 Admin → Data Streams → Measurement Protocol), `YM_OAUTH_TOKEN` (Яндекс OAuth с доступом к счётчику) — в переменные Amvera.
- Деплой правок лендинга: `git push master` в репо `russianlineup-site`.
- `SITE_ORIGIN` (домен лендинга) для CORS — в ENV бота.

## Вне скоупа (v1)

- Загрузка продаж (price) — поле есть, заполнение позже.
- Пер-IP лимит на `/api/token`.
- GA4-события для прямых стартов без ga4_cid (не атрибутируемы — не шлём).
- Дашборд-визуализация источников/конверсий из GA4/Метрики (смотрим в самих системах).

## Фазовость / порядок

Фаза 1 (фундамент) — первой; Фазы 2 (GA4) и 3 (Метрика) независимы между собой, обе поверх Фазы 1. Каждая фаза ENV-gated и деплоится самостоятельно.
