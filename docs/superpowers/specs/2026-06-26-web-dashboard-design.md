Project: ruslineup-bot
Document: design-spec

# Этап 8 — Дашборд: `/stats` в боте + веб-морда

_2026-06-26 · FED-245 · ветка `fedrbodr/fed-245-etap-8-dashbord-svodnie-metriki`_

## Цель

Дать владельцу сводную аналитику по боту двумя способами: командой `/stats` в Telegram (быстрый взгляд) и небольшой защищённой веб-страницей (воронка + последние заявки). Источник — те же таблицы Postgres `events`, `leads`, `promo`, `users`.

## Подход

aiohttp-веб поднимается **в том же процессе бота** (aiohttp уже идёт зависимостью aiogram): один asyncio event-loop крутит и `dp.start_polling(bot)`, и веб-сервер. Отдельный сервис на Amvera отклонён для v1 (лишняя инфра; общее состояние — только БД).

Агрегаты считаются **один раз** в `bot/services/stats.py` и переиспользуются и командой, и вебом — единая логика, без дублирования SQL.

## Компоненты

- **`bot/services/stats.py`** — чистый слой агрегатов поверх пула `asyncpg`. Функции read-only, no-op-безопасны без пула (возвращают пустую сводку). Возвращает дата-класс `Stats` со счётчиками + список последних заявок.
- **`bot/handlers/stats.py`** — команда `/stats`. **Только админ**: отвечает, только если `str(message.from_user.id) == settings.admin_chat_id`; иначе молча игнор (или короткий «нет доступа»). Рендерит текстовую сводку.
- **`bot/web.py`** — aiohttp-приложение: middleware Basic-auth (креды из ENV), один GET-роут `/` — server-rendered HTML (минимум inline-CSS, без внешнего JS/CDN). Показывает воронку + таблицу последних заявок с маскированным контактом. Фабрика `build_app()` возвращает `web.Application` (тестируется отдельно от сервера).
- **`bot/__main__.py`** — если заданы `DASHBOARD_USER` и `DASHBOARD_PASSWORD`, поднимаем веб через `web.AppRunner`/`TCPSite` на `settings.web_port` рядом с поллингом; иначе — лог-предупреждение и работаем без веба. Веб гасим в `finally` вместе с пулом.
- **`bot/config.py`** + **`.env.example`**: `DASHBOARD_USER`, `DASHBOARD_PASSWORD` (секрет!), `WEB_PORT` (env `PORT`/`WEB_PORT`, дефолт `8080`).

## Данные / метрики (`Stats`)

- `starts_total`, `starts_today`, `starts_7d`
- `starts_by_source: list[(utm_source, count)]` (топ источников)
- `faq_by_topic: list[(detail, count)]` (event=`faq_click`)
- `leads_total`, `leads_by_type: list[(type, count)]`, конверсия `start→lead` (%)
- `promo_total`, конверсия `start→promo` (%)
- `recent_leads: list[Lead]` — последние 20 (ts, name, city, type, contact_masked, utm_source)

Старты считаются как `count(*) FROM events WHERE event='start'`; конверсии — отношение к `starts_total` (если 0 — показываем `—`, без деления на ноль). Период «сегодня»/«7 дней» — по `ts` в UTC.

## Доступ / безопасность

- Basic-auth на **всех** роутах веба (middleware сравнивает с `DASHBOARD_USER`/`DASHBOARD_PASSWORD` через `secrets.compare_digest`). Нет кредов → веб не поднимается.
- Контакт маскируется **всегда**, даже под авторизацией: `+79265803341` → `+7926***3341` (видны первые 5 и последние 4 цифры, середина — `***`). Короткие/нестандартные значения маскируются целиком.
- `DASHBOARD_PASSWORD` — только ENV/секреты Amvera. Репозиторий публичный: в коде/`.env.example` только пустые плейсхолдеры.
- `/stats` в боте — только владелец (`admin_chat_id`).

## Предусловие деплоя (требует действий в Amvera)

Сейчас приложение — worker (HTTP-порт не слушает). Для веб-морды нужно, чтобы **Amvera отдавала HTTP-порт/домен** на это приложение. Перед деплоем: включить веб/проброс порта в Amvera и задать `DASHBOARD_USER`/`DASHBOARD_PASSWORD`. Бот слушает порт из `WEB_PORT`/`PORT`. Без этих переменных всё остальное (бот, `/stats`) работает по-прежнему.

## Тестирование (TDD)

- **`stats.py`** — юнит с фейковым пулом (как в `tests/test_db.py`): проверяем, что выполняется ожидаемый SQL и результат маппится в `Stats`; ветка «нет пула» → пустая сводка.
- **маскировка** — юнит на чистую функцию `mask_contact`.
- **`/stats` handler** — гейт «только админ» (чужой id → нет сводки), формат сводки (мок `stats`).
- **`web.py`** — через `aiohttp.test_utils` (`TestClient`): `GET /` без кредов → `401`; с верными → `200` и HTML содержит ключевые цифры; контакт в HTML замаскирован; неверный пароль → `401`.

## Вне скоупа (v1)

- Standalone SQL-вьюхи/Metabase (агрегаты живут в `stats.py`; добавим позже при необходимости).
- Графики/JS-визуализация — только текст/таблица.
- Пагинация заявок, фильтры, экспорт.
- Кэширование агрегатов (объёмы малы — считаем на лету).
