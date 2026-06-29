# Сквозная аналитика (токены + GA4 + Метрика) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Связать веб-визит (лендинг) с действиями в боте через короткий токен и слать серверные конверсии в GA4 (реалтайм) и Яндекс.Метрику (оффлайн, авто-выгрузка).

**Architecture:** Лендинг при клике регистрирует токен (`POST /api/token` на боте) с GA4/Metrika ClientID + utm, открывает `t.me/bot?start=tok_<id>`. Бот по токену сохраняет cid/utm на пользователя и шлёт события: GA4 Measurement Protocol на старт/заявку/промокод; конверсии копятся в БД и батчем уходят в Метрику фоновой задачей. Всё внешнее ENV-gated и best-effort.

**Tech Stack:** Python 3.11 · aiogram 3 · aiohttp (вход и исход) · asyncpg · pytest (asyncio_mode=auto). Лендинг — статический `index.html` (отдельный репо).

## Global Constraints

- Секреты `GA4_API_SECRET`, `YM_OAUTH_TOKEN` — только ENV. `GA4_MEASUREMENT_ID` (`G-6XY6XFGE6H`), `YM_COUNTER_ID` (`110157768`) — публичные, в ENV для гибкости.
- Все внешние вызовы (GA4/Метрика/свой `/api/token`) best-effort: сбой не ломает флоу бота. ENV-gated: нет креда → no-op.
- `/api/token` — публичный (без Basic-auth), CORS только на `SITE_ORIGIN` (дефолт `https://russianlineup.ru`). Middleware пропускает `/health` и `/api/token`.
- `/start` поддерживает `tok_<id>`, legacy `<src>__<cid>` и голый utm.
- В юнит-тестах нет реальных вызовов GA4/Метрики и реального HTTP к боту (aiohttp TestClient для своего эндпоинта; исходящие POST мокаются). Слой БД — мок пула (как `tests/test_db.py`).
- TDD, атомарные коммиты. Тесты: `PYTHONPATH=. pytest`.

---

## ФАЗА 1 — Фундамент (склейка)

### Task 1: Config + .env

**Files:** Modify `bot/config.py`, `.env.example`; Test `tests/test_config.py`

**Interfaces:** Produces `settings.ga4_measurement_id`, `ga4_api_secret`, `ym_counter_id`, `ym_oauth_token`, `ym_upload_interval: int`, `site_origin`.

- [ ] **Step 1: Failing test** (в `tests/test_config.py`)
```python
def test_analytics_fields():
    from bot.config import Settings
    s = Settings(ga4_api_secret="sec", ym_oauth_token="tok",
                 ym_upload_interval=900, site_origin="https://x")
    assert s.ga4_measurement_id == "G-6XY6XFGE6H"  # дефолт
    assert s.ga4_api_secret == "sec"
    assert s.ym_counter_id == "110157768"  # дефолт
    assert s.ym_oauth_token == "tok"
    assert s.ym_upload_interval == 900
    assert s.site_origin == "https://x"
```
- [ ] **Step 2:** `PYTHONPATH=. pytest tests/test_config.py::test_analytics_fields -v` → FAIL.
- [ ] **Step 3:** В `Settings` (после `ai_daily_limit`) добавить:
```python
    # Сквозная аналитика (этап 7)
    ga4_measurement_id: str = os.getenv("GA4_MEASUREMENT_ID", "G-6XY6XFGE6H")
    ga4_api_secret: str = os.getenv("GA4_API_SECRET", "")
    ym_counter_id: str = os.getenv("YM_COUNTER_ID", "110157768")
    ym_oauth_token: str = os.getenv("YM_OAUTH_TOKEN", "")
    ym_upload_interval: int = int(os.getenv("YM_UPLOAD_INTERVAL") or "1800")
    site_origin: str = os.getenv("SITE_ORIGIN", "https://russianlineup.ru")
```
- [ ] **Step 4:** В `.env.example` добавить:
```
# Сквозная аналитика (этап 7)
GA4_MEASUREMENT_ID=G-6XY6XFGE6H
GA4_API_SECRET=
YM_COUNTER_ID=110157768
YM_OAUTH_TOKEN=
YM_UPLOAD_INTERVAL=1800
SITE_ORIGIN=https://russianlineup.ru
```
- [ ] **Step 5:** `PYTHONPATH=. pytest tests/test_config.py -v` → PASS.
- [ ] **Step 6: Commit** `feat(config): ENV для сквозной аналитики (GA4/Метрика/SITE_ORIGIN)`

---

### Task 2: БД — tokens + cids на users

**Files:** Modify `bot/services/db.py`; Test `tests/test_db.py`

**Interfaces:** Produces (no-op-safe без пула):
- `async insert_token(*, token, ga4_cid, ym_cid, utm_source, utm_medium, utm_campaign) -> None`
- `async get_token(token: str) -> dict | None`
- `async link_token_user(*, token: str, user_id: int) -> None`
- `async set_user_cids(*, user_id: int, ga4_cid: str | None, ym_cid: str | None) -> None`
- `async get_user_cids(user_id: int) -> dict` (ключи `ga4_cid`, `ym_cid`)
- `init_schema` создаёт таблицу `tokens` и добавляет колонки `ga4_cid`, `ym_cid` в `users`.

- [ ] **Step 1: Failing test** (в `tests/test_db.py`, используя тамошние `FakeConn`/`FakePool`)
```python
@pytest.mark.asyncio
async def test_insert_and_get_token():
    conn = FakeConn()
    conn.fetchrow = AsyncMock(return_value={"token": "abc", "ga4_cid": "g", "ym_cid": "y",
        "utm_source": "youtube", "utm_medium": "video", "utm_campaign": "c1"})
    db.set_pool(FakePool(conn))
    try:
        await db.insert_token(token="abc", ga4_cid="g", ym_cid="y",
            utm_source="youtube", utm_medium="video", utm_campaign="c1")
        assert "INSERT INTO tokens" in conn.execute.await_args.args[0]
        tok = await db.get_token("abc")
    finally:
        db.set_pool(None)
    assert tok["ga4_cid"] == "g" and tok["utm_source"] == "youtube"


@pytest.mark.asyncio
async def test_set_and_get_user_cids():
    conn = FakeConn()
    conn.fetchrow = AsyncMock(return_value={"ga4_cid": "g1", "ym_cid": "y1"})
    db.set_pool(FakePool(conn))
    try:
        await db.set_user_cids(user_id=7, ga4_cid="g1", ym_cid="y1")
        assert "UPDATE users" in conn.execute.await_args.args[0]
        cids = await db.get_user_cids(7)
    finally:
        db.set_pool(None)
    assert cids == {"ga4_cid": "g1", "ym_cid": "y1"}


@pytest.mark.asyncio
async def test_token_helpers_no_pool():
    db.set_pool(None)
    assert await db.get_token("x") is None
    assert await db.get_user_cids(1) == {"ga4_cid": None, "ym_cid": None}
```
- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3:** В `bot/services/db.py` добавить DDL и провести в `init_schema`:
```python
CREATE_TOKENS = """
CREATE TABLE IF NOT EXISTS tokens (
    token        TEXT PRIMARY KEY,
    ga4_cid      TEXT,
    ym_cid       TEXT,
    utm_source   TEXT,
    utm_medium   TEXT,
    utm_campaign TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    user_id      BIGINT
)
"""
```
  В `init_schema` после создания `users` добавить:
```python
        await conn.execute(CREATE_TOKENS)
        await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS ga4_cid TEXT")
        await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS ym_cid TEXT")
```
  И функции:
```python
async def insert_token(*, token, ga4_cid, ym_cid, utm_source, utm_medium, utm_campaign) -> None:
    if _pool is None:
        return
    sql = ("INSERT INTO tokens(token, ga4_cid, ym_cid, utm_source, utm_medium, utm_campaign) "
           "VALUES($1, $2, $3, $4, $5, $6) ON CONFLICT (token) DO NOTHING")
    async with _pool.acquire() as conn:
        await conn.execute(sql, token, ga4_cid, ym_cid, utm_source, utm_medium, utm_campaign)


async def get_token(token: str):
    if _pool is None:
        return None
    sql = ("SELECT token, ga4_cid, ym_cid, utm_source, utm_medium, utm_campaign "
           "FROM tokens WHERE token = $1")
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(sql, token)
        return dict(row) if row else None


async def link_token_user(*, token: str, user_id: int) -> None:
    if _pool is None:
        return
    async with _pool.acquire() as conn:
        await conn.execute("UPDATE tokens SET user_id = $2 WHERE token = $1", token, user_id)


async def set_user_cids(*, user_id: int, ga4_cid, ym_cid) -> None:
    if _pool is None:
        return
    sql = ("UPDATE users SET ga4_cid = COALESCE($2, ga4_cid), ym_cid = COALESCE($3, ym_cid) "
           "WHERE user_id = $1")
    async with _pool.acquire() as conn:
        await conn.execute(sql, user_id, ga4_cid, ym_cid)


async def get_user_cids(user_id: int) -> dict:
    if _pool is None:
        return {"ga4_cid": None, "ym_cid": None}
    async with _pool.acquire() as conn:
        row = await conn.fetchrow("SELECT ga4_cid, ym_cid FROM users WHERE user_id = $1", user_id)
        return dict(row) if row else {"ga4_cid": None, "ym_cid": None}
```
- [ ] **Step 4:** run → PASS.
- [ ] **Step 5: Commit** `feat(db): таблица tokens + ga4_cid/ym_cid на users`

---

### Task 3: Эндпоинт `POST /api/token` + CORS

**Files:** Modify `bot/web.py`; Test `tests/test_web.py`

**Interfaces:** Consumes `db.insert_token`, `settings.site_origin`. Produces routes `POST /api/token` (→ `{"token": <hex12>}` + CORS) и `OPTIONS /api/token` (→ 204 + CORS); middleware пропускает `/api/token` и `/health` без авторизации.

- [ ] **Step 1: Failing test** (в `tests/test_web.py`)
```python
@pytest.mark.asyncio
async def test_api_token_public_with_cors(monkeypatch):
    monkeypatch.setattr(web, "settings", types.SimpleNamespace(
        dashboard_user="a", dashboard_password="b", site_origin="https://russianlineup.ru"))
    insert = AsyncMock()
    monkeypatch.setattr(web.db, "insert_token", insert)
    async with TestClient(TestServer(web.build_app())) as cli:
        resp = await cli.post("/api/token", json={"ga4_cid": "g", "ym_cid": "y",
                                                  "utm_source": "youtube"})
        assert resp.status == 200
        data = await resp.json()
        assert data["token"] and len(data["token"]) == 12
        assert resp.headers["Access-Control-Allow-Origin"] == "https://russianlineup.ru"
        opt = await cli.options("/api/token")
        assert opt.status == 204
    insert.assert_awaited_once()
    assert insert.await_args.kwargs["ga4_cid"] == "g"
```
  (Также `tests/test_web.py` уже импортирует `bot.web as web`; `web.db` — модуль `bot.services.db`, который надо импортировать в `web.py`.)
- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3:** В `bot/web.py`:
  - вверху добавить `import secrets` и `import bot.services.db as db`.
  - в middleware `_auth_mw` заменить условие пропуска:
```python
    if request.path in ("/health", "/api/token"):
        return await handler(request)
```
  - добавить:
```python
def _cors_headers() -> dict:
    return {
        "Access-Control-Allow-Origin": settings.site_origin,
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
    }


async def _register_token(request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    token = secrets.token_hex(6)
    await db.insert_token(
        token=token,
        ga4_cid=body.get("ga4_cid"),
        ym_cid=body.get("ym_cid"),
        utm_source=body.get("utm_source"),
        utm_medium=body.get("utm_medium"),
        utm_campaign=body.get("utm_campaign"),
    )
    return web.json_response({"token": token}, headers=_cors_headers())


async def _token_options(request):
    return web.Response(status=204, headers=_cors_headers())
```
  - в `build_app` добавить роуты:
```python
    app.router.add_post("/api/token", _register_token)
    app.router.add_options("/api/token", _token_options)
```
- [ ] **Step 4:** run → PASS (и весь `tests/test_web.py` зелёный — авторизация дашборда не сломана).
- [ ] **Step 5: Commit** `feat(web): публичный POST /api/token (регистрация токена) + CORS`

---

### Task 4: `/start` — разбор tok_/legacy/plain + сохранение cid

**Files:** Modify `bot/handlers/start.py`; Test `tests/test_start_handler.py`

**Interfaces:** Consumes `db.get_token`, `db.link_token_user`, `db.set_user_cids`, `db.upsert_user_utm`, `log_event`.

- [ ] **Step 1: Failing test** (в `tests/test_start_handler.py`)
```python
@pytest.mark.asyncio
async def test_cmd_start_token(monkeypatch):
    monkeypatch.setattr(start, "log_event", AsyncMock())
    monkeypatch.setattr(start.db, "get_token", AsyncMock(return_value={
        "ga4_cid": "g1", "ym_cid": "y1", "utm_source": "youtube"}))
    link = AsyncMock(); setcids = AsyncMock(); upsert = AsyncMock()
    monkeypatch.setattr(start.db, "link_token_user", link)
    monkeypatch.setattr(start.db, "set_user_cids", setcids)
    monkeypatch.setattr(start.db, "upsert_user_utm", upsert)
    user = SimpleNamespace(id=7, username="neo")
    message = SimpleNamespace(from_user=user, answer=AsyncMock())
    await start.cmd_start(message, SimpleNamespace(args="tok_deadbeef0000"))
    assert upsert.await_args.kwargs["utm_source"] == "youtube"
    assert setcids.await_args.kwargs == {"user_id": 7, "ga4_cid": "g1", "ym_cid": "y1"}
    link.assert_awaited_once()


@pytest.mark.asyncio
async def test_cmd_start_legacy_cid(monkeypatch):
    monkeypatch.setattr(start, "log_event", AsyncMock())
    monkeypatch.setattr(start.db, "upsert_user_utm", AsyncMock())
    setcids = AsyncMock()
    monkeypatch.setattr(start.db, "set_user_cids", setcids)
    user = SimpleNamespace(id=7, username="neo")
    message = SimpleNamespace(from_user=user, answer=AsyncMock())
    await start.cmd_start(message, SimpleNamespace(args="hero__123456789"))
    assert setcids.await_args.kwargs["ym_cid"] == "123456789"
```
  (Существующие тесты `test_cmd_start_logs_utm_and_upserts` / `test_cmd_start_defaults_to_direct` должны продолжать проходить — они шлют `args="youtube"`/`None`; добавь в них at-need `monkeypatch.setattr(start.db, "set_user_cids", AsyncMock())`.)
- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3:** Переписать тело `cmd_start` в `bot/handlers/start.py`:
```python
@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject) -> None:
    user = message.from_user
    args = command.args or ""
    utm, ga4_cid, ym_cid = "direct", None, None
    if args.startswith("tok_"):
        tok = await db.get_token(args[len("tok_"):])
        if tok:
            utm = tok.get("utm_source") or "direct"
            ga4_cid = tok.get("ga4_cid")
            ym_cid = tok.get("ym_cid")
            await db.link_token_user(token=args[len("tok_"):], user_id=user.id)
    elif "__" in args:
        src, _, cid = args.partition("__")
        utm = src or "direct"
        ym_cid = cid or None
    elif args:
        utm = args
    await db.upsert_user_utm(user_id=user.id, username=user.username, utm_source=utm)
    await db.set_user_cids(user_id=user.id, ga4_cid=ga4_cid, ym_cid=ym_cid)
    await log_event(user, event="start", detail="", utm=utm)
    await message.answer(WELCOME, reply_markup=main_menu())
```
- [ ] **Step 4:** run → PASS (весь suite).
- [ ] **Step 5: Commit** `feat(start): разбор tok_/legacy ClientID + сохранение cid на пользователя`

---

### Task 5: Лендинг — регистрация токена (отдельный репо)

**Files:** Modify `/Users/d.fedorenko/IdeaProjects/fedrbodr/russianlineup-site/index.html`

Тестов нет (статический сайт). После правки — ручная проверка (клик → Network → бот получает `tok_`).

- [ ] **Step 1:** В IIFE заменить тело обработчика `.js-bot` так, чтобы перед редиректом регистрировать токен. Точная логика:
```javascript
var BOT_API = "https://ruslineup-bot-fedrbodr.amvera.io/api/token";

function ga4ClientId(cb){
  try{ if(window.gtag && CFG.ga4Id){ gtag('get', CFG.ga4Id, 'client_id', function(id){ cb(id||""); }); return; } }catch(_){}
  cb("");
}

document.querySelectorAll(".js-bot").forEach(function(el){
  el.addEventListener("click", function(e){
    e.preventDefault();
    var params = new URLSearchParams(window.location.search);
    var src = params.get("utm_source") || this.dataset.src || "site";
    try{ if(window.gtag) gtag("event","open_bot",{source:src}); }catch(_){}
    try{ if(window.ym && CFG.ymCounterId) ym(CFG.ymCounterId,"reachGoal","open_bot"); }catch(_){}

    withClientId(function(ymCid){           // существующий захват Metrika ClientID
      ga4ClientId(function(gaCid){
        var payload = { ga4_cid: gaCid, ym_cid: ymCid, utm_source: src,
          utm_medium: params.get("utm_medium")||"", utm_campaign: params.get("utm_campaign")||"" };
        var done = false;
        function go(url){ if(!done){ done = true; window.location.href = url; } }
        // фолбэк через 1.2с — если API не ответил, открываем legacy-ссылку
        setTimeout(function(){ go(botLink(src, ymCid)); }, 1200);
        fetch(BOT_API, {method:"POST", headers:{"Content-Type":"application/json"},
                        body: JSON.stringify(payload)})
          .then(function(r){ return r.json(); })
          .then(function(d){ if(d && d.token){ go("https://t.me/"+CFG.botUsername+"?start=tok_"+d.token); } })
          .catch(function(){ /* фолбэк сработает по таймауту */ });
      });
    });
  });
});
```
- [ ] **Step 2:** Локально открыть `index.html`, кликнуть кнопку, в DevTools→Network убедиться: POST на `/api/token` → `{token}`, редирект на `t.me/...?start=tok_<token>`. Если API недоступен — через 1.2с открывается legacy `start=src__cid`.
- [ ] **Step 3: Commit (в репо лендинга)** `feat: регистрация токена сквозной аналитики перед открытием бота` и `git push master` (деплой по FTP).

---

## ФАЗА 2 — GA4 (Measurement Protocol)

### Task 6: `bot/services/ga4.py`

**Files:** Create `bot/services/ga4.py`; Test `tests/test_ga4.py`

**Interfaces:** Produces `async send_event(client_id: str, name: str, params: dict | None = None) -> None` (ENV-gated, best-effort) и внутренний `async _post(url, payload)` (мокается в тестах).

- [ ] **Step 1: Failing test**
```python
# tests/test_ga4.py
import types
import pytest
from unittest.mock import AsyncMock
import bot.services.ga4 as ga4


@pytest.mark.asyncio
async def test_send_event_posts(monkeypatch):
    monkeypatch.setattr(ga4, "settings", types.SimpleNamespace(
        ga4_measurement_id="G-X", ga4_api_secret="sec"))
    post = AsyncMock()
    monkeypatch.setattr(ga4, "_post", post)
    await ga4.send_event("cid123", "bot_start", {"src": "youtube"})
    url, payload = post.await_args.args
    assert "measurement_id=G-X" in url and "api_secret=sec" in url
    assert payload["client_id"] == "cid123"
    assert payload["events"][0]["name"] == "bot_start"


@pytest.mark.asyncio
async def test_send_event_noop_without_secret(monkeypatch):
    monkeypatch.setattr(ga4, "settings", types.SimpleNamespace(
        ga4_measurement_id="G-X", ga4_api_secret=""))
    post = AsyncMock()
    monkeypatch.setattr(ga4, "_post", post)
    await ga4.send_event("cid", "bot_start")
    post.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_event_noop_without_client_id(monkeypatch):
    monkeypatch.setattr(ga4, "settings", types.SimpleNamespace(
        ga4_measurement_id="G-X", ga4_api_secret="sec"))
    post = AsyncMock()
    monkeypatch.setattr(ga4, "_post", post)
    await ga4.send_event("", "bot_start")
    post.assert_not_awaited()
```
- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3: Impl**
```python
# bot/services/ga4.py
"""GA4 Measurement Protocol (этап 7): серверные события бота. Best-effort, ENV-gated."""
import logging

import aiohttp

from bot.config import settings

logger = logging.getLogger("ga4")
_COLLECT = "https://www.google-analytics.com/mp/collect"


async def _post(url: str, payload: dict) -> None:
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as resp:
            await resp.read()


async def send_event(client_id: str, name: str, params: dict | None = None) -> None:
    if not (settings.ga4_measurement_id and settings.ga4_api_secret and client_id):
        return
    url = (f"{_COLLECT}?measurement_id={settings.ga4_measurement_id}"
           f"&api_secret={settings.ga4_api_secret}")
    payload = {"client_id": client_id, "events": [{"name": name, "params": params or {}}]}
    try:
        await _post(url, payload)
    except Exception:
        logger.warning("GA4 send_event failed (best-effort)", exc_info=True)
```
- [ ] **Step 4:** run → PASS.
- [ ] **Step 5: Commit** `feat(ga4): send_event через Measurement Protocol (ENV-gated)`

---

### Task 7: Подключить GA4-события в хендлеры

**Files:** Modify `bot/handlers/start.py`, `bot/handlers/lead.py`, `bot/handlers/promo.py`; Test `tests/test_start_handler.py`, `tests/test_lead.py`, `tests/test_promo.py`

**Interfaces:** Consumes `ga4.send_event`, `db.get_user_cids`. События: `bot_start` (start, если ga4_cid из токена), `lead_submit` (lead), `promo_issue` (promo) с client_id из `get_user_cids`.

- [ ] **Step 1: Failing test** — в `tests/test_start_handler.py` (token-кейс) добавить:
```python
    sent = AsyncMock(); monkeypatch.setattr(start.ga4, "send_event", sent)
    # ... после await start.cmd_start(...):
    assert sent.await_args.args[1] == "bot_start"
```
  В `tests/test_lead.py::test_finish_inserts_lead_notifies_admin_and_logs` добавить:
```python
    monkeypatch.setattr(lead.db, "get_user_cids", AsyncMock(return_value={"ga4_cid": "g", "ym_cid": None}))
    sent = AsyncMock(); monkeypatch.setattr(lead.ga4, "send_event", sent)
    # после _finish: assert sent.await_args.args[1] == "lead_submit"
```
  В `tests/test_promo.py::test_promo_get_shows_code_nick_and_discount` добавить:
```python
    monkeypatch.setattr(promo.db, "get_user_cids", AsyncMock(return_value={"ga4_cid": "g", "ym_cid": None}))
    sent = AsyncMock(); monkeypatch.setattr(promo.ga4, "send_event", sent)
    # после on_promo_get: assert sent.await_args.args[1] == "promo_issue"
```
- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3: Impl**
  - `start.py`: `import bot.services.ga4 as ga4`; в `cmd_start` после `set_user_cids` (только в tok_ ветке, где есть ga4_cid):
```python
    if ga4_cid:
        await ga4.send_event(ga4_cid, "bot_start", {"utm_source": utm})
```
  - `lead.py`: `import bot.services.ga4 as ga4`; в `_finish` после `log_event(...)`:
```python
    cids = await db.get_user_cids(user.id)
    if cids.get("ga4_cid"):
        await ga4.send_event(cids["ga4_cid"], "lead_submit", {"type": lead_type})
```
  - `promo.py`: `import bot.services.ga4 as ga4`; в `on_promo_get` после `log_event(...)`:
```python
    cids = await db.get_user_cids(user.id)
    if cids.get("ga4_cid"):
        await ga4.send_event(cids["ga4_cid"], "promo_issue", {"code": code})
```
- [ ] **Step 4:** run → PASS (весь suite).
- [ ] **Step 5: Commit** `feat(ga4): bot_start/lead_submit/promo_issue в хендлерах`

---

## ФАЗА 3 — Метрика (оффлайн-конверсии)

### Task 8: БД — таблица conversions

**Files:** Modify `bot/services/db.py`; Test `tests/test_db.py`

**Interfaces:** Produces:
- `async enqueue_conversion(*, user_id, ym_cid, target, price=None) -> None`
- `async fetch_pending_conversions(limit=1000) -> list[dict]` (поля `id, ts, ym_cid, target, price`)
- `async mark_conversions_uploaded(ids: list[int]) -> None`
- `init_schema` создаёт `conversions`.

- [ ] **Step 1: Failing test**
```python
@pytest.mark.asyncio
async def test_conversions_flow():
    conn = FakeConn()
    conn.fetch = AsyncMock(return_value=[{"id": 1, "ts": None, "ym_cid": "y", "target": "lead", "price": None}])
    db.set_pool(FakePool(conn))
    try:
        await db.enqueue_conversion(user_id=7, ym_cid="y", target="lead")
        assert "INSERT INTO conversions" in conn.execute.await_args.args[0]
        rows = await db.fetch_pending_conversions()
        assert rows[0]["target"] == "lead"
        await db.mark_conversions_uploaded([1, 2])
        assert "UPDATE conversions" in conn.execute.await_args.args[0]
    finally:
        db.set_pool(None)
```
- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3:** В `bot/services/db.py` добавить DDL + провести в `init_schema`:
```python
CREATE_CONVERSIONS = """
CREATE TABLE IF NOT EXISTS conversions (
    id        BIGSERIAL PRIMARY KEY,
    ts        TIMESTAMPTZ NOT NULL DEFAULT now(),
    user_id   BIGINT,
    ym_cid    TEXT,
    target    TEXT,
    price     NUMERIC,
    uploaded  BOOLEAN NOT NULL DEFAULT false
)
"""
```
  (в `init_schema`: `await conn.execute(CREATE_CONVERSIONS)`)
  Функции:
```python
async def enqueue_conversion(*, user_id: int, ym_cid: str, target: str, price=None) -> None:
    if _pool is None:
        return
    sql = "INSERT INTO conversions(user_id, ym_cid, target, price) VALUES($1, $2, $3, $4)"
    async with _pool.acquire() as conn:
        await conn.execute(sql, user_id, ym_cid, target, price)


async def fetch_pending_conversions(limit: int = 1000) -> list:
    if _pool is None:
        return []
    sql = ("SELECT id, ts, ym_cid, target, price FROM conversions "
           "WHERE uploaded = false AND ym_cid IS NOT NULL ORDER BY id LIMIT $1")
    async with _pool.acquire() as conn:
        return [dict(r) for r in await conn.fetch(sql, limit)]


async def mark_conversions_uploaded(ids: list) -> None:
    if _pool is None or not ids:
        return
    async with _pool.acquire() as conn:
        await conn.execute("UPDATE conversions SET uploaded = true WHERE id = ANY($1)", ids)
```
- [ ] **Step 4:** run → PASS.
- [ ] **Step 5: Commit** `feat(db): таблица conversions + enqueue/fetch_pending/mark_uploaded`

---

### Task 9: `bot/services/metrika.py` — батч-выгрузка

**Files:** Create `bot/services/metrika.py`; Test `tests/test_metrika.py`

**Interfaces:** Produces `async upload_pending() -> int` (ENV-gated, best-effort), `_build_csv(rows) -> str` (чистая), `async _upload(csv_text) -> bool` (мокается).

- [ ] **Step 1: Failing test**
```python
# tests/test_metrika.py
import types
import pytest
from unittest.mock import AsyncMock
import bot.services.metrika as metrika


def test_build_csv():
    rows = [{"id": 1, "ts": None, "ym_cid": "y1", "target": "lead", "price": None}]
    csv_text = metrika._build_csv(rows)
    assert csv_text.splitlines()[0] == "ClientId,Target,DateTime,Price,Currency"
    assert "y1,lead," in csv_text


@pytest.mark.asyncio
async def test_upload_pending_marks(monkeypatch):
    monkeypatch.setattr(metrika, "settings", types.SimpleNamespace(
        ym_oauth_token="t", ym_counter_id="111"))
    monkeypatch.setattr(metrika.db, "fetch_pending_conversions",
                        AsyncMock(return_value=[{"id": 1, "ts": None, "ym_cid": "y", "target": "lead", "price": None}]))
    monkeypatch.setattr(metrika, "_upload", AsyncMock(return_value=True))
    mark = AsyncMock(); monkeypatch.setattr(metrika.db, "mark_conversions_uploaded", mark)
    n = await metrika.upload_pending()
    assert n == 1
    assert mark.await_args.args[0] == [1]


@pytest.mark.asyncio
async def test_upload_pending_noop_without_token(monkeypatch):
    monkeypatch.setattr(metrika, "settings", types.SimpleNamespace(ym_oauth_token="", ym_counter_id="111"))
    fetch = AsyncMock(); monkeypatch.setattr(metrika.db, "fetch_pending_conversions", fetch)
    assert await metrika.upload_pending() == 0
    fetch.assert_not_awaited()
```
- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3: Impl**
```python
# bot/services/metrika.py
"""Яндекс.Метрика оффлайн-конверсии (этап 7): батч-выгрузка по ClientID. ENV-gated."""
import csv
import io
import logging

import aiohttp

import bot.services.db as db
from bot.config import settings

logger = logging.getLogger("metrika")


def _build_csv(rows) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["ClientId", "Target", "DateTime", "Price", "Currency"])
    for r in rows:
        ts = r.get("ts")
        dt = int(ts.timestamp()) if ts is not None else 0
        writer.writerow([r["ym_cid"], r["target"], dt, r.get("price") or "", "RUB"])
    return buf.getvalue()


async def _upload(csv_text: str) -> bool:
    url = (f"https://api-metrika.yandex.net/management/v1/counter/{settings.ym_counter_id}"
           f"/offline_conversions/upload?client_id_type=CLIENT_ID")
    headers = {"Authorization": f"OAuth {settings.ym_oauth_token}"}
    data = aiohttp.FormData()
    data.add_field("file", csv_text, filename="conversions.csv", content_type="text/csv")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=data, headers=headers) as resp:
                return resp.status < 300
    except Exception:
        logger.warning("Metrika upload failed (best-effort)", exc_info=True)
        return False


async def upload_pending() -> int:
    if not (settings.ym_oauth_token and settings.ym_counter_id):
        return 0
    rows = await db.fetch_pending_conversions()
    if not rows:
        return 0
    if await _upload(_build_csv(rows)):
        await db.mark_conversions_uploaded([r["id"] for r in rows])
        return len(rows)
    return 0
```
- [ ] **Step 4:** run → PASS.
- [ ] **Step 5: Commit** `feat(metrika): батч-выгрузка оффлайн-конверсий (ENV-gated)`

---

### Task 10: Enqueue конверсий в хендлеры

**Files:** Modify `bot/handlers/lead.py`, `bot/handlers/promo.py`; Test `tests/test_lead.py`, `tests/test_promo.py`

**Interfaces:** Consumes `db.enqueue_conversion`, `db.get_user_cids`. На `lead_submit`/`promo_issue` ставим конверсию, если у юзера есть `ym_cid`.

- [ ] **Step 1: Failing test** — в `tests/test_lead.py` (тот же finish-тест) добавить `get_user_cids` с `ym_cid="y"` и:
```python
    enq = AsyncMock(); monkeypatch.setattr(lead.db, "enqueue_conversion", enq)
    # после _finish:
    assert enq.await_args.kwargs["target"] == "lead"
    assert enq.await_args.kwargs["ym_cid"] == "y"
```
  В `tests/test_promo.py` аналогично для `target == "promo"`.
- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3: Impl** — переиспользовать уже полученный в Task 7 `cids` (один вызов `get_user_cids`):
  - `lead.py` `_finish`, рядом с GA4-блоком:
```python
    if cids.get("ym_cid"):
        await db.enqueue_conversion(user_id=user.id, ym_cid=cids["ym_cid"], target="lead")
```
  - `promo.py` `on_promo_get`, рядом с GA4-блоком:
```python
    if cids.get("ym_cid"):
        await db.enqueue_conversion(user_id=user.id, ym_cid=cids["ym_cid"], target="promo")
```
- [ ] **Step 4:** run → PASS.
- [ ] **Step 5: Commit** `feat(metrika): enqueue конверсий lead/promo при наличии ym_cid`

---

### Task 11: Фоновый аплоадер в `__main__`

**Files:** Modify `bot/__main__.py`

**Interfaces:** Если заданы YM-креды — asyncio-задача раз в `settings.ym_upload_interval` сек зовёт `metrika.upload_pending()`; гасится в shutdown.

- [ ] **Step 1:** Юнит-теста нет (интеграция). Импорт-smoke: `PYTHONPATH=. python -c "import bot.__main__"` → OK.
- [ ] **Step 2: Impl** — в `bot/__main__.py`:
  - импорт: `import bot.services.metrika as metrika`.
  - корутина (вне `main`):
```python
async def _metrika_uploader() -> None:
    while True:
        await asyncio.sleep(settings.ym_upload_interval)
        try:
            n = await metrika.upload_pending()
            if n:
                logging.getLogger("metrika").info("Uploaded %s conversions to Metrika", n)
        except Exception:
            logging.getLogger("metrika").warning("uploader tick failed", exc_info=True)
```
  - в `main`, после старта веба/перед polling:
```python
    uploader = None
    if settings.ym_oauth_token and settings.ym_counter_id:
        uploader = asyncio.create_task(_metrika_uploader())
        log.info("Metrika uploader started (interval %ss)", settings.ym_upload_interval)
```
  - в `finally` перед `await db.close_pool()`:
```python
        if uploader is not None:
            uploader.cancel()
```
- [ ] **Step 3:** `PYTHONPATH=. pytest -q` → зелёное; импорт-smoke OK.
- [ ] **Step 4: Commit** `feat(app): фоновая выгрузка конверсий в Метрику`

---

### Task 12: README + .env доки

**Files:** Modify `README.md`

- [ ] **Step 1:** Добавить раздел «Сквозная аналитика (этап 7)»: токен лендинг↔бот (`/api/token`), GA4 Measurement Protocol (`GA4_API_SECRET`), Метрика оффлайн-конверсии (`YM_OAUTH_TOKEN`, авто-выгрузка раз в `YM_UPLOAD_INTERVAL`), `SITE_ORIGIN` для CORS. Обновить список ENV в разделе деплоя.
- [ ] **Step 2: Commit** `docs: README — раздел про сквозную аналитику`

---

## Self-Review

- **Spec coverage:** tokens+cids (T2), `/api/token`+CORS (T3), `/start` разбор (T4), лендинг (T5), GA4 send_event (T6) + события в хендлерах (T7), conversions (T8), metrika выгрузка (T9) + enqueue (T10), фоновый аплоадер (T11), config/env (T1), README (T12). ✓
- **Phasing:** Фаза 1 (T1–T5) → Фаза 2 (T6–T7) → Фаза 3 (T8–T11), все ENV-gated. ✓
- **Type consistency:** `get_token`→dict, `get_user_cids`→{ga4_cid,ym_cid}, `send_event(client_id,name,params)`, `enqueue_conversion(*,user_id,ym_cid,target,price)`, `upload_pending()->int`, `fetch_pending_conversions`/`mark_conversions_uploaded` — совпадают между задачами. ✓
- **Один `get_user_cids` на хендлер:** T7 вводит `cids = await db.get_user_cids(...)`, T10 переиспользует ту же переменную (не дублирует вызов). ✓
- **Security:** секреты только ENV; `/api/token` публичный но только пишет токены; внешние вызовы best-effort. ✓
- **No live external calls in tests:** `_post`/`_upload`/`send_event` мокаются; `/api/token` через TestClient. ✓
