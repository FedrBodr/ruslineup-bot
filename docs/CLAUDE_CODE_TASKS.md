# Задачи для Claude Code

Готовые промпты по этапам ТЗ. Бери по одному, выполняй в репозитории, гоняй тесты, коммить.

> ⚠️ **Принцип безопасности (репозиторий публичный):** никаких чувствительных данных в коде и в `knowledge.md` — реальные цены, условия предзаказа, размер скидки партнёра, личные контакты читаем ТОЛЬКО из ENV (`BOARD_PRICE`, `PREORDER_TERMS`, `TESTDAY_PRICE`, `PARTNER_DISCOUNT`, `PARTNER_NICK`). Тексты FAQ держим обобщёнными, конкретику подставляем из переменных.

## Этап 1 — Каркас ✅ (готов)
Бот отвечает на `/start` с inline-меню. `promocode` + тесты.

## Этап 2 — Метрики в Google Sheets
> В `bot/services/sheets.py` реализуй подключение к Google Sheets через gspread + service account (`GOOGLE_SERVICE_ACCOUNT_JSON`, `SHEET_ID`). Добавь `append_event(...)` для листа `events` с колонками: timestamp, user_id, username, utm_source, event, detail. Подключи вызов в `metrics.log_event` (убери TODO). Создай лист, если его нет. Напиши тест с моком gspread.

## Этап 3 — FAQ-кнопки
> Создай `bot/handlers/faq.py` и `bot/content/faq.py`. На callback `faq:boards|camps|community` отвечай готовым текстом с под-кнопками («Оставить заявку», «Назад»). Каждое нажатие логируй через `log_event(event="faq_click", detail=<тема>)`. Зарегистрируй роутер в `__main__`.

## Этап 4 — Заявки (FSM)
> Создай `bot/handlers/lead.py` с FSM-диалогом: имя → город → контакт (+ кнопка «поделиться контактом») → опц. комментарий. По завершении пиши строку в лист `leads` и шли уведомление в `ADMIN_CHAT_ID`. Логируй `event="lead_submit"`. Триггеры: callback `lead:testday` и кнопка из FAQ.

## Этап 5 — Промокоды
> Создай `bot/handlers/promo.py`: на callback `promo:get` сгенерируй код через `generate_code(user.id)`, запиши в лист `promo` (код, user_id, username, дата, статус «выдан»), покажи код + `PARTNER_NICK`. Повторный запрос отдаёт тот же код (проверяй наличие в листе). Логируй `event="promo_issue"`.

## Этап 6 — AI-фолбэк
> Создай `bot/services/llm.py` и `bot/content/knowledge.md`. На callback `ai:ask` переключай в режим ожидания вопроса; свободный текст → LLM-ответ по базе знаний (system-prompt + knowledge.md). Если уверенность низкая — предложи написать админу. Логируй `event="ask_ai"` с текстом вопроса и флагом эскалации.

## Этап 7 — Сквозная аналитика
> Добавь лист `tokens` и склейку лендинг↔бот: deep-link `start=<токен>` сопоставляй с web ClientID. Реализуй отправку ключевых событий в GA4 через Measurement Protocol (`bot_start`, `lead_submit`, `promo_issue`) с client_id из токена. Конфиг GA4 — через ENV.

## Этап 8 — Дашборд
> Добавь лист `dashboard` со сводными формулами поверх `events`/`leads`/`promo`: старты по дням и по utm_source, клики по темам, заявки и конверсия start→lead, промокоды и конверсия start→promo.

## Этап 9 — Деплой
> Проверь сборку на Amvera, прогон smoke-теста в проде: `/start`, нажатие кнопок, заявка, промокод. Зафиксируй чек-лист в README.
