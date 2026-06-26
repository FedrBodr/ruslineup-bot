# Дашборд (/stats + веб-морда) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Сводная аналитика бота двумя способами — команда `/stats` (только админ) и защищённая Basic-auth веб-страница (воронка + последние заявки с маскированным контактом).

**Architecture:** Единый слой агрегатов `bot/services/stats.py` поверх пула `asyncpg` (тот же `db._pool`); переиспользуется командой и вебом. aiohttp-веб поднимается в том же процессе бота рядом с поллингом. Источник — таблицы `events/leads/promo`.

**Tech Stack:** Python 3.11 · aiogram 3 · aiohttp (транзитивно из aiogram) · asyncpg · pytest (asyncio_mode=auto).

## Global Constraints

- Репозиторий ПУБЛИЧНЫЙ: `DASHBOARD_PASSWORD` и прочие секреты — только ENV; в `.env.example` пустые плейсхолдеры.
- Контакт маскируется ВСЕГДА в слое данных (`get_stats`), не в рендере — PII не покидает `stats.py` в открытом виде.
- `/stats` отвечает только если `str(message.from_user.id) == settings.admin_chat_id`.
- Веб поднимается только если заданы `DASHBOARD_USER` и `DASHBOARD_PASSWORD`; иначе бот работает как раньше.
- Тесты: `PYTHONPATH=. pytest`. Запуск одного: `PYTHONPATH=. pytest tests/test_x.py::test_y -v`.

---

### Task 1: Конфиг + .env.example

**Files:**
- Modify: `bot/config.py`
- Modify: `.env.example`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `settings.dashboard_user: str`, `settings.dashboard_password: str`, `settings.web_port: int`.

- [ ] **Step 1: Failing test** (добавить в `tests/test_config.py`)
```python
def test_dashboard_and_port_fields():
    from bot.config import Settings
    s = Settings(dashboard_user="admin", dashboard_password="pw", web_port=9000)
    assert s.dashboard_user == "admin"
    assert s.dashboard_password == "pw"
    assert s.web_port == 9000
```
- [ ] **Step 2:** `PYTHONPATH=. pytest tests/test_config.py::test_dashboard_and_port_fields -v` → FAIL (нет полей).
- [ ] **Step 3:** В `bot/config.py` в `Settings` добавить:
```python
    # Веб-дашборд (этап 8)
    dashboard_user: str = os.getenv("DASHBOARD_USER", "")
    dashboard_password: str = os.getenv("DASHBOARD_PASSWORD", "")
    web_port: int = int(os.getenv("WEB_PORT") or os.getenv("PORT") or "8080")
```
- [ ] **Step 4:** В `.env.example` добавить блок:
```
# Веб-дашборд (этап 8) — секреты, только ENV
DASHBOARD_USER=
DASHBOARD_PASSWORD=
WEB_PORT=8080
```
- [ ] **Step 5:** `PYTHONPATH=. pytest tests/test_config.py -v` → PASS.
- [ ] **Step 6: Commit** `feat(config): ENV для веб-дашборда (DASHBOARD_USER/PASSWORD/WEB_PORT)`

---

### Task 2: `stats.mask_contact` + дата-классы

**Files:**
- Create: `bot/services/stats.py`
- Test: `tests/test_stats.py`

**Interfaces:**
- Produces:
  - `mask_contact(contact: str) -> str` — `+79265803341` → `+7926***3341`; короче 9 символов → `***`; пусто → `""`.
  - `@dataclass Lead`: `ts: str, name: str, city: str, type: str, contact: str, utm_source: str`.
  - `@dataclass Stats`: `starts_total:int, starts_today:int, starts_7d:int, starts_by_source:list[tuple[str,int]], faq_by_topic:list[tuple[str,int]], leads_total:int, leads_by_type:list[tuple[str,int]], promo_total:int, recent_leads:list[Lead]` + методы `lead_conv()->str`, `promo_conv()->str` (процент или `—`), и classmethod `empty()`.

- [ ] **Step 1: Failing test**
```python
# tests/test_stats.py
from bot.services.stats import mask_contact, Stats


def test_mask_phone():
    assert mask_contact("+79265803341") == "+7926***3341"


def test_mask_short_and_empty():
    assert mask_contact("@neo") == "***"
    assert mask_contact("") == ""


def test_conversion_and_empty():
    s = Stats.empty()
    assert s.starts_total == 0
    assert s.lead_conv() == "—"  # деления на ноль нет
    s2 = Stats(starts_total=100, starts_today=0, starts_7d=0, starts_by_source=[],
               faq_by_topic=[], leads_total=25, leads_by_type=[], promo_total=10,
               recent_leads=[])
    assert s2.lead_conv() == "25%"
    assert s2.promo_conv() == "10%"
```
- [ ] **Step 2:** run → FAIL (нет модуля).
- [ ] **Step 3: Minimal impl**
```python
# bot/services/stats.py
from __future__ import annotations
from dataclasses import dataclass, field


def mask_contact(contact: str) -> str:
    c = (contact or "").strip()
    if len(c) >= 9:
        return f"{c[:5]}***{c[-4:]}"
    return "***" if c else ""


@dataclass
class Lead:
    ts: str
    name: str
    city: str
    type: str
    contact: str
    utm_source: str


@dataclass
class Stats:
    starts_total: int
    starts_today: int
    starts_7d: int
    starts_by_source: list
    faq_by_topic: list
    leads_total: int
    leads_by_type: list
    promo_total: int
    recent_leads: list

    @classmethod
    def empty(cls) -> "Stats":
        return cls(0, 0, 0, [], [], 0, [], 0, [])

    def _pct(self, n: int) -> str:
        if not self.starts_total:
            return "—"
        return f"{round(n * 100 / self.starts_total)}%"

    def lead_conv(self) -> str:
        return self._pct(self.leads_total)

    def promo_conv(self) -> str:
        return self._pct(self.promo_total)
```
- [ ] **Step 4:** run → PASS.
- [ ] **Step 5: Commit** `feat(stats): mask_contact + дата-классы Stats/Lead`

---

### Task 3: `stats.get_stats` (агрегаты из Postgres)

**Files:**
- Modify: `bot/services/stats.py`
- Test: `tests/test_stats.py`

**Interfaces:**
- Consumes: `bot.services.db._pool` (глобальный пул; как в `tests/test_db.py`), его `acquire()` → conn с `fetchval`/`fetch`.
- Produces: `async def get_stats() -> Stats` — без пула возвращает `Stats.empty()`. Контакт в `recent_leads` уже замаскирован через `mask_contact`.
  - Порядок `fetchval`: starts_total, starts_today, starts_7d, leads_total, promo_total.
  - Порядок `fetch`: starts_by_source, faq_by_topic, leads_by_type, recent_leads.

- [ ] **Step 1: Failing test**
```python
import pytest
from unittest.mock import AsyncMock
import bot.services.db as db
import bot.services.stats as stats


class FakeConn:
    def __init__(self, vals, rows):
        self.fetchval = AsyncMock(side_effect=vals)
        self.fetch = AsyncMock(side_effect=rows)


class FakePool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        conn = self._conn

        class _Acq:
            async def __aenter__(s):
                return conn

            async def __aexit__(s, *a):
                return False

        return _Acq()


@pytest.mark.asyncio
async def test_get_stats_maps_and_masks():
    vals = [100, 10, 40, 25, 15]  # starts_total, today, 7d, leads, promo
    rows = [
        [{"utm_source": "youtube", "c": 60}],          # by source
        [{"detail": "boards", "c": 30}],               # faq by topic
        [{"type": "testday", "c": 20}],                # leads by type
        [{"ts": "2026-06-26 03:38", "name": "Дмитрий", "city": "Москва",
          "type": "preorder", "contact": "+79265803341", "utm_source": "direct"}],
    ]
    db.set_pool(FakePool(FakeConn(vals, rows)))
    try:
        s = await stats.get_stats()
    finally:
        db.set_pool(None)
    assert s.starts_total == 100
    assert s.leads_total == 25
    assert s.promo_total == 15
    assert s.lead_conv() == "25%"
    assert s.starts_by_source == [("youtube", 60)]
    assert s.recent_leads[0].contact == "+7926***3341"  # замаскирован
    assert s.recent_leads[0].name == "Дмитрий"


@pytest.mark.asyncio
async def test_get_stats_no_pool_is_empty():
    db.set_pool(None)
    s = await stats.get_stats()
    assert s.starts_total == 0
    assert s.recent_leads == []
```
- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3: Minimal impl** (добавить в `bot/services/stats.py`)
```python
import bot.services.db as db


async def get_stats() -> Stats:
    pool = db._pool
    if pool is None:
        return Stats.empty()
    async with pool.acquire() as conn:
        starts_total = await conn.fetchval(
            "SELECT count(*) FROM events WHERE event = 'start'") or 0
        starts_today = await conn.fetchval(
            "SELECT count(*) FROM events WHERE event='start' AND ts::date = now()::date") or 0
        starts_7d = await conn.fetchval(
            "SELECT count(*) FROM events WHERE event='start' AND ts >= now() - interval '7 days'") or 0
        leads_total = await conn.fetchval("SELECT count(*) FROM leads") or 0
        promo_total = await conn.fetchval("SELECT count(*) FROM promo") or 0

        src = await conn.fetch(
            "SELECT coalesce(utm_source,'') AS utm_source, count(*) AS c "
            "FROM events WHERE event='start' GROUP BY 1 ORDER BY c DESC LIMIT 10")
        faq = await conn.fetch(
            "SELECT coalesce(detail,'') AS detail, count(*) AS c "
            "FROM events WHERE event='faq_click' GROUP BY 1 ORDER BY c DESC LIMIT 10")
        by_type = await conn.fetch(
            "SELECT coalesce(type,'') AS type, count(*) AS c FROM leads GROUP BY 1 ORDER BY c DESC")
        recent = await conn.fetch(
            "SELECT to_char(ts,'YYYY-MM-DD HH24:MI') AS ts, coalesce(name,'') AS name, "
            "coalesce(city,'') AS city, coalesce(type,'') AS type, coalesce(contact,'') AS contact, "
            "coalesce(utm_source,'') AS utm_source FROM leads ORDER BY ts DESC LIMIT 20")

    return Stats(
        starts_total=starts_total,
        starts_today=starts_today,
        starts_7d=starts_7d,
        starts_by_source=[(r["utm_source"], r["c"]) for r in src],
        faq_by_topic=[(r["detail"], r["c"]) for r in faq],
        leads_total=leads_total,
        leads_by_type=[(r["type"], r["c"]) for r in by_type],
        promo_total=promo_total,
        recent_leads=[
            Lead(ts=r["ts"], name=r["name"], city=r["city"], type=r["type"],
                 contact=mask_contact(r["contact"]), utm_source=r["utm_source"])
            for r in recent
        ],
    )
```
- [ ] **Step 4:** run → PASS.
- [ ] **Step 5: Commit** `feat(stats): get_stats — агрегаты воронки + последние заявки (контакт маскируется)`

---

### Task 4: Команда `/stats` (только админ)

**Files:**
- Create: `bot/handlers/stats.py`
- Test: `tests/test_stats_handler.py`

**Interfaces:**
- Consumes: `stats.get_stats`, `settings.admin_chat_id`.
- Produces: `router`; `async def cmd_stats(message)`; `render_text(s: Stats) -> str`.

- [ ] **Step 1: Failing test**
```python
# tests/test_stats_handler.py
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock
import bot.handlers.stats as h
from bot.services.stats import Stats


def _msg(user_id):
    return SimpleNamespace(from_user=SimpleNamespace(id=user_id, username="u"),
                           answer=AsyncMock())


@pytest.mark.asyncio
async def test_stats_ignored_for_non_admin(monkeypatch):
    monkeypatch.setattr(h, "settings", SimpleNamespace(admin_chat_id="999"))
    monkeypatch.setattr(h, "get_stats", AsyncMock(return_value=Stats.empty()))
    m = _msg(123)  # не админ
    await h.cmd_stats(m)
    m.answer.assert_not_awaited()


@pytest.mark.asyncio
async def test_stats_shown_to_admin(monkeypatch):
    monkeypatch.setattr(h, "settings", SimpleNamespace(admin_chat_id="999"))
    s = Stats(starts_total=100, starts_today=5, starts_7d=40, starts_by_source=[("youtube", 60)],
              faq_by_topic=[], leads_total=25, leads_by_type=[("testday", 20)], promo_total=10,
              recent_leads=[])
    monkeypatch.setattr(h, "get_stats", AsyncMock(return_value=s))
    m = _msg(999)  # админ
    await h.cmd_stats(m)
    m.answer.assert_awaited_once()
    text = m.answer.await_args.args[0]
    assert "100" in text and "25" in text
```
- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3: Minimal impl**
```python
# bot/handlers/stats.py
"""Команда /stats — сводка для админа (этап 8)."""
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.config import settings
from bot.services.stats import Stats, get_stats

router = Router()


def render_text(s: Stats) -> str:
    src = ", ".join(f"{name or 'direct'}: {c}" for name, c in s.starts_by_source) or "—"
    types = ", ".join(f"{t or '—'}: {c}" for t, c in s.leads_by_type) or "—"
    return (
        "📊 Статистика\n"
        f"Старты: {s.starts_total} (сегодня {s.starts_today}, 7 дней {s.starts_7d})\n"
        f"Источники: {src}\n"
        f"Заявки: {s.leads_total} ({types}) · конверсия start→lead {s.lead_conv()}\n"
        f"Промокоды: {s.promo_total} · конверсия start→promo {s.promo_conv()}"
    )


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    if str(message.from_user.id) != settings.admin_chat_id:
        return  # тихо игнорируем не-админа
    s = await get_stats()
    await message.answer(render_text(s))
```
- [ ] **Step 4:** run → PASS.
- [ ] **Step 5:** Зарегистрировать роутер в `bot/__main__.py`: добавить `stats` в `from bot.handlers import ...` и `dp.include_router(stats.router)`. Прогнать `PYTHONPATH=. pytest -q` → всё зелёное.
- [ ] **Step 6: Commit** `feat(stats): команда /stats для админа`

---

### Task 5: Веб-морда (aiohttp + Basic-auth)

**Files:**
- Create: `bot/web.py`
- Test: `tests/test_web.py`

**Interfaces:**
- Consumes: `settings.dashboard_user/password`, `stats.get_stats`.
- Produces: `build_app() -> web.Application` (middleware Basic-auth + GET `/`); `render_html(s: Stats) -> str`.

- [ ] **Step 1: Failing test**
```python
# tests/test_web.py
import base64
import pytest
from unittest.mock import AsyncMock
from aiohttp.test_utils import TestClient, TestServer
import bot.web as web
from bot.services.stats import Stats, Lead


def _auth(u, p):
    return "Basic " + base64.b64encode(f"{u}:{p}".encode()).decode()


@pytest.fixture
def sample():
    return Stats(starts_total=100, starts_today=5, starts_7d=40,
                 starts_by_source=[("youtube", 60)], faq_by_topic=[("boards", 30)],
                 leads_total=25, leads_by_type=[("testday", 20)], promo_total=10,
                 recent_leads=[Lead("2026-06-26 03:38", "Дмитрий", "Москва",
                                    "preorder", "+7926***3341", "direct")])


@pytest.mark.asyncio
async def test_requires_auth(monkeypatch, sample):
    import types
    monkeypatch.setattr(web, "settings", types.SimpleNamespace(dashboard_user="a", dashboard_password="b"))
    monkeypatch.setattr(web, "get_stats", AsyncMock(return_value=sample))
    async with TestClient(TestServer(web.build_app())) as cli:
        assert (await cli.get("/")).status == 401
        assert (await cli.get("/", headers={"Authorization": _auth("a", "wrong")})).status == 401


@pytest.mark.asyncio
async def test_ok_with_auth_and_masked(monkeypatch, sample):
    import types
    monkeypatch.setattr(web, "settings", types.SimpleNamespace(dashboard_user="a", dashboard_password="b"))
    monkeypatch.setattr(web, "get_stats", AsyncMock(return_value=sample))
    async with TestClient(TestServer(web.build_app())) as cli:
        resp = await cli.get("/", headers={"Authorization": _auth("a", "b")})
        assert resp.status == 200
        html = await resp.text()
        assert "100" in html and "25" in html
        assert "+7926***3341" in html
        assert "5803341" not in html  # полный телефон НЕ светится
```
- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3: Minimal impl**
```python
# bot/web.py
"""Веб-дашборд (этап 8): Basic-auth, одна страница с воронкой и заявками."""
import base64
import secrets
from html import escape

from aiohttp import web

from bot.config import settings
from bot.services.stats import Stats, get_stats


def _authorized(header: str) -> bool:
    if not header.startswith("Basic "):
        return False
    try:
        user, _, pwd = base64.b64decode(header[6:]).decode().partition(":")
    except Exception:
        return False
    return (secrets.compare_digest(user, settings.dashboard_user)
            and secrets.compare_digest(pwd, settings.dashboard_password))


@web.middleware
async def _auth_mw(request, handler):
    if not _authorized(request.headers.get("Authorization", "")):
        return web.Response(status=401, text="401",
                            headers={"WWW-Authenticate": 'Basic realm="dashboard"'})
    return await handler(request)


def render_html(s: Stats) -> str:
    rows = "".join(
        f"<tr><td>{escape(l.ts)}</td><td>{escape(l.name)}</td><td>{escape(l.city)}</td>"
        f"<td>{escape(l.type)}</td><td>{escape(l.contact)}</td><td>{escape(l.utm_source)}</td></tr>"
        for l in s.recent_leads
    )
    src = "".join(f"<li>{escape(n or 'direct')}: {c}</li>" for n, c in s.starts_by_source)
    return (
        "<!doctype html><meta charset='utf-8'><title>ruslineup dashboard</title>"
        "<style>body{font-family:sans-serif;margin:2rem;max-width:900px}"
        "table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccc;padding:4px 8px}"
        "h1{font-size:1.3rem}</style>"
        "<h1>📊 Русский Лайнап — дашборд</h1>"
        f"<p>Старты: <b>{s.starts_total}</b> (сегодня {s.starts_today}, 7 дней {s.starts_7d})</p>"
        f"<p>Заявки: <b>{s.leads_total}</b> · конверсия start→lead {s.lead_conv()}</p>"
        f"<p>Промокоды: <b>{s.promo_total}</b> · конверсия start→promo {s.promo_conv()}</p>"
        f"<p>Источники стартов:</p><ul>{src}</ul>"
        "<h2>Последние заявки</h2>"
        "<table><tr><th>Когда</th><th>Имя</th><th>Город</th><th>Тип</th>"
        f"<th>Контакт</th><th>Источник</th></tr>{rows}</table>"
    )


async def _index(request):
    return web.Response(text=render_html(await get_stats()), content_type="text/html")


def build_app() -> web.Application:
    app = web.Application(middlewares=[_auth_mw])
    app.router.add_get("/", _index)
    return app
```
- [ ] **Step 4:** run → PASS.
- [ ] **Step 5: Commit** `feat(web): Basic-auth дашборд (воронка + заявки, контакт маскирован)`

---

### Task 6: Поднять веб рядом с поллингом в `__main__`

**Files:**
- Modify: `bot/__main__.py`

**Interfaces:**
- Consumes: `web.build_app()`, `settings.dashboard_user/password/web_port`.
- Поведение: если заданы оба креда — поднять `web.AppRunner`/`TCPSite` на `0.0.0.0:web_port` до `start_polling`; погасить в `finally`. Иначе — лог-предупреждение, веб не поднимается.

- [ ] **Step 1:** Юнит-теста нет (интеграция). Импорт-smoke: `PYTHONPATH=. python -c "import bot.__main__"` → без ошибок.
- [ ] **Step 2:** В `bot/__main__.py` импортировать `from aiohttp import web as aioweb` и `from bot import web as dashboard`; после создания `dp`/перед `start_polling`:
```python
    runner = None
    if settings.dashboard_user and settings.dashboard_password:
        runner = aioweb.AppRunner(dashboard.build_app())
        await runner.setup()
        await aioweb.TCPSite(runner, host="0.0.0.0", port=settings.web_port).start()
        log.info("Web dashboard on :%s", settings.web_port)
    else:
        log.warning("DASHBOARD_USER/PASSWORD не заданы — веб-дашборд выключен")
```
и обернуть polling:
```python
    try:
        await dp.start_polling(bot)
    finally:
        if runner is not None:
            await runner.cleanup()
        await db.close_pool()
```
- [ ] **Step 3:** `PYTHONPATH=. pytest -q` → всё зелёное; импорт-smoke ОК.
- [ ] **Step 4: Commit** `feat(app): поднимать веб-дашборд рядом с поллингом (если заданы креды)`

---

### Task 7: README — раздел про дашборд

**Files:**
- Modify: `README.md`

- [ ] **Step 1:** Добавить в README короткий раздел: `/stats` (только админ); веб-дашборд по Basic-auth на `WEB_PORT`; переменные `DASHBOARD_USER`/`DASHBOARD_PASSWORD`; предусловие — Amvera должна отдавать HTTP-порт. Обновить список ENV.
- [ ] **Step 2: Commit** `docs: README — раздел про /stats и веб-дашборд`

---

## Self-Review

- **Spec coverage:** stats-слой (T2,T3) ✓; `/stats` админ-гейт (T4) ✓; веб Basic-auth + маскировка (T5) ✓; запуск рядом с поллингом (T6) ✓; config/ENV (T1) ✓; деплой-предусловие → README (T7) + спек ✓; тесты на каждый ✓.
- **Маскировка** применяется в `get_stats` (T3), веб только отображает — PII не выходит из слоя данных открытым. ✓
- **Type consistency:** `Stats`/`Lead` поля и сигнатуры (`get_stats`, `mask_contact`, `render_text`, `render_html`, `build_app`) совпадают между задачами. ✓
- **No standalone SQL views** — вне скоупа (спек). ✓
