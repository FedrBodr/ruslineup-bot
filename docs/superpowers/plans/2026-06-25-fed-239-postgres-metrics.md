# FED-239 — Этап 2: Метрики в PostgreSQL Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Этап-1 logging stub with a PostgreSQL-backed metrics layer: every bot event is persisted to an `events` table, and `utm_source` (which arrives only at `/start`) is persisted per-user so later events stay attributed.

**Architecture:** A thin async data layer (`bot/services/db.py`) owns an `asyncpg` pool and exposes `append_event`, `upsert_user_utm`, `get_user_utm`, plus idempotent schema init. `metrics.log_event` becomes async and routes through it. The pool is injected (a module-level holder set at startup, replaceable in tests) so unit tests mock `asyncpg` with no live DB.

**Tech Stack:** Python 3.11 · aiogram 3 · asyncpg · pytest (asyncio).

## Global Constraints

- Repo is PUBLIC: no secrets/sensitive data in code or tests. `DATABASE_URL` via ENV only.
- Python 3.11 (Amvera target); run tests with `PYTHONPATH=. pytest`.
- aiogram is async — `log_event` and all DB calls are `async`; the one existing call site (`start.py`) migrates with it.
- First-touch attribution: a user's stored `utm_source` is set on first `/start` and not overwritten later.
- TDD: failing test → minimal impl → green → commit. Atomic commits per task.

---

### Task 1: Config + dependencies (DATABASE_URL, asyncpg)

**Files:**
- Modify: `requirements.txt`
- Modify: `bot/config.py`
- Modify: `.env.example`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `settings.database_url: str` (from ENV `DATABASE_URL`, default `""`).

- [ ] **Step 1: Failing test**
```python
# tests/test_config.py
import importlib, os

def test_database_url_from_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h:5432/db")
    import bot.config as cfg
    importlib.reload(cfg)
    assert cfg.settings.database_url == "postgresql://u:p@h:5432/db"
```
- [ ] **Step 2:** `PYTHONPATH=. pytest tests/test_config.py -v` → FAIL (no attribute `database_url`).
- [ ] **Step 3:** In `bot/config.py` add `database_url: str = os.getenv("DATABASE_URL", "")`; remove `sheet_id` and `google_sa_json` (gspread is gone).
- [ ] **Step 4:** In `requirements.txt` remove `gspread==6.1.2` and `google-auth==2.34.0`, add `asyncpg==0.30.0`. In `.env.example` remove `SHEET_ID`/`GOOGLE_SERVICE_ACCOUNT_JSON`, add `DATABASE_URL=postgresql://user:pass@host:5432/ruslineup`.
- [ ] **Step 5:** `pip install -r requirements.txt`; `PYTHONPATH=. pytest tests/test_config.py -v` → PASS.
- [ ] **Step 6: Commit** `feat(db): add DATABASE_URL config, swap gspread→asyncpg deps`

---

### Task 2: `db.append_event` against a mocked pool

**Files:**
- Create: `bot/services/db.py`
- Test: `tests/test_db.py`

**Interfaces:**
- Produces:
  - `set_pool(pool) -> None` / `get_pool() -> Pool` (module-level holder `_pool`).
  - `async def append_event(*, user_id: int, username: str | None, utm_source: str, event: str, detail: str = "", ts: datetime | None = None) -> None` — `INSERT INTO events(ts, user_id, username, utm_source, event, detail) VALUES(...)`; `ts` defaults to `now()` in SQL when None.
- Consumes (test): a fake pool whose `acquire()` is an async context manager yielding a conn with `execute` (AsyncMock).

- [ ] **Step 1: Failing test**
```python
# tests/test_db.py
import pytest
from unittest.mock import AsyncMock, MagicMock
import bot.services.db as db

class FakeConn:
    def __init__(self): self.execute = AsyncMock()
class FakePool:
    def __init__(self, conn): self._conn = conn
    def acquire(self):
        conn = self._conn
        class _Acq:
            async def __aenter__(self_inner): return conn
            async def __aexit__(self_inner, *a): return False
        return _Acq()

@pytest.mark.asyncio
async def test_append_event_inserts_row():
    conn = FakeConn(); db.set_pool(FakePool(conn))
    await db.append_event(user_id=42, username="neo", utm_source="youtube",
                          event="start", detail="tok_1")
    assert conn.execute.await_count == 1
    sql = conn.execute.await_args.args[0]
    assert "INSERT INTO events" in sql
    assert conn.execute.await_args.args[1:] == (42, "neo", "youtube", "start", "tok_1")
```
- [ ] **Step 2:** `PYTHONPATH=. pytest tests/test_db.py -v` → FAIL (module/func missing).
- [ ] **Step 3: Minimal impl**
```python
# bot/services/db.py
from __future__ import annotations
from datetime import datetime
from typing import Optional
import asyncpg  # noqa: F401  (used at runtime for pool creation)

_pool = None

def set_pool(pool) -> None:
    global _pool
    _pool = pool

def get_pool():
    if _pool is None:
        raise RuntimeError("DB pool is not initialised — call init_pool() at startup")
    return _pool

async def append_event(*, user_id: int, username: Optional[str], utm_source: str,
                       event: str, detail: str = "", ts: Optional[datetime] = None) -> None:
    sql = (
        "INSERT INTO events(ts, user_id, username, utm_source, event, detail) "
        "VALUES(COALESCE($6, now()), $1, $2, $3, $4, $5)"
    )
    async with get_pool().acquire() as conn:
        await conn.execute(sql, user_id, username, utm_source, event, detail, ts)
```
  (Test asserts positional args `(42,"neo","youtube","start","tok_1")` — adjust the assertion to include the trailing `ts=None` if you keep `$6`; simplest: bind `ts` last and assert `args[1:6]`.)
- [ ] **Step 4:** `PYTHONPATH=. pytest tests/test_db.py -v` → PASS.
- [ ] **Step 5: Commit** `feat(db): append_event writes to events via asyncpg pool`

---

### Task 3: `users` utm persistence (`upsert_user_utm`, `get_user_utm`)

**Files:**
- Modify: `bot/services/db.py`
- Test: `tests/test_db.py`

**Interfaces:**
- Produces:
  - `async def upsert_user_utm(*, user_id: int, username: str | None, utm_source: str) -> None` — `INSERT ... ON CONFLICT(user_id) DO UPDATE SET username=EXCLUDED.username` (utm kept first-touch via `utm_source = COALESCE(users.utm_source, EXCLUDED.utm_source)`).
  - `async def get_user_utm(user_id: int) -> str | None` — `SELECT utm_source FROM users WHERE user_id=$1`; uses `conn.fetchval`.

- [ ] **Step 1: Failing test** (add to `tests/test_db.py`)
```python
@pytest.mark.asyncio
async def test_upsert_user_utm_first_touch():
    conn = FakeConn(); db.set_pool(FakePool(conn))
    await db.upsert_user_utm(user_id=42, username="neo", utm_source="youtube")
    sql = conn.execute.await_args.args[0]
    assert "INSERT INTO users" in sql and "ON CONFLICT" in sql and "COALESCE" in sql

@pytest.mark.asyncio
async def test_get_user_utm_returns_value():
    conn = FakeConn(); conn.fetchval = AsyncMock(return_value="instagram")
    db.set_pool(FakePool(conn))
    assert await db.get_user_utm(42) == "instagram"
```
- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3:** Implement both; `get_user_utm` uses `conn.fetchval(sql, user_id)`. (Add `fetchval` to `FakeConn` default = AsyncMock.)
- [ ] **Step 4:** run → PASS.
- [ ] **Step 5: Commit** `feat(db): persist per-user utm (first-touch) in users table`

---

### Task 4: Idempotent schema init

**Files:**
- Modify: `bot/services/db.py`
- Test: `tests/test_db.py`

**Interfaces:**
- Produces:
  - `async def init_schema() -> None` — runs `CREATE TABLE IF NOT EXISTS events(...)` and `users(...)`.
  - `async def init_pool(dsn: str) -> None` — `set_pool(await asyncpg.create_pool(dsn))` then `await init_schema()`. (Not unit-tested; covered by integration/startup.)

- [ ] **Step 1: Failing test**
```python
@pytest.mark.asyncio
async def test_init_schema_creates_tables():
    conn = FakeConn(); db.set_pool(FakePool(conn))
    await db.init_schema()
    ddl = " ".join(c.args[0] for c in conn.execute.await_args_list)
    assert "CREATE TABLE IF NOT EXISTS events" in ddl
    assert "CREATE TABLE IF NOT EXISTS users" in ddl
```
- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3:** Implement `init_schema` (two `await conn.execute(DDL)` calls inside one `acquire()`), columns: events(id bigserial pk, ts timestamptz default now(), user_id bigint, username text, utm_source text, event text, detail text); users(user_id bigint primary key, username text, utm_source text, created_at timestamptz default now()). Add `init_pool`.
- [ ] **Step 4:** run → PASS.
- [ ] **Step 5: Commit** `feat(db): idempotent schema init for events + users`

---

### Task 5: `metrics.log_event` async, wired to db

**Files:**
- Modify: `bot/services/metrics.py`
- Test: `tests/test_metrics.py`

**Interfaces:**
- Consumes: `db.append_event`, `db.get_user_utm`.
- Produces: `async def log_event(user, event: str, detail: str = "", utm: str | None = None) -> None` — resolves source as `utm if utm is not None else (await db.get_user_utm(user.id))`; logs; awaits `db.append_event(...)`. Never raises on DB failure (wrap in try/except + log warning) so a metrics hiccup can't break the user flow.

- [ ] **Step 1: Failing test**
```python
# tests/test_metrics.py
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock
import bot.services.metrics as metrics

@pytest.mark.asyncio
async def test_log_event_explicit_utm_appends(monkeypatch):
    append = AsyncMock()
    monkeypatch.setattr(metrics.db, "append_event", append)
    monkeypatch.setattr(metrics.db, "get_user_utm", AsyncMock(return_value=None))
    user = SimpleNamespace(id=7, username="trinity")
    await metrics.log_event(user, event="start", detail="", utm="youtube")
    append.assert_awaited_once()
    assert append.await_args.kwargs["utm_source"] == "youtube"
    assert append.await_args.kwargs["event"] == "start"

@pytest.mark.asyncio
async def test_log_event_resolves_stored_utm(monkeypatch):
    append = AsyncMock()
    monkeypatch.setattr(metrics.db, "append_event", append)
    monkeypatch.setattr(metrics.db, "get_user_utm", AsyncMock(return_value="instagram"))
    user = SimpleNamespace(id=7, username="trinity")
    await metrics.log_event(user, event="faq_click", detail="boards")
    assert append.await_args.kwargs["utm_source"] == "instagram"

@pytest.mark.asyncio
async def test_log_event_swallows_db_error(monkeypatch):
    monkeypatch.setattr(metrics.db, "append_event", AsyncMock(side_effect=RuntimeError("db down")))
    monkeypatch.setattr(metrics.db, "get_user_utm", AsyncMock(return_value=None))
    user = SimpleNamespace(id=7, username="trinity")
    await metrics.log_event(user, event="start", utm="direct")  # must not raise
```
- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3:** Rewrite `metrics.py`: `import bot.services.db as db`; async `log_event` per the interface, try/except around the db calls logging a warning on failure.
- [ ] **Step 4:** run → PASS.
- [ ] **Step 5: Commit** `feat(metrics): async log_event persists events + resolves utm`

---

### Task 6: `start.py` — upsert utm + fixed log_event call

**Files:**
- Modify: `bot/handlers/start.py`
- Test: `tests/test_start_handler.py`

**Interfaces:**
- Consumes: `db.upsert_user_utm`, `metrics.log_event`.
- Behavior: parse `utm = command.args or "direct"`; `await db.upsert_user_utm(user_id, username, utm)`; `await log_event(user, event="start", detail="", utm=utm)` (utm now in its own param, **not** `detail`); answer welcome + menu.

- [ ] **Step 1: Failing test**
```python
# tests/test_start_handler.py
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock
import bot.handlers.start as start

@pytest.mark.asyncio
async def test_cmd_start_logs_utm_and_upserts(monkeypatch):
    log = AsyncMock(); upsert = AsyncMock()
    monkeypatch.setattr(start, "log_event", log)
    monkeypatch.setattr(start.db, "upsert_user_utm", upsert)
    user = SimpleNamespace(id=7, username="trinity")
    message = SimpleNamespace(from_user=user, answer=AsyncMock())
    command = SimpleNamespace(args="youtube")
    await start.cmd_start(message, command)
    assert upsert.await_args.kwargs["utm_source"] == "youtube"
    assert log.await_args.kwargs["utm"] == "youtube"
    assert log.await_args.kwargs["event"] == "start"
    message.answer.assert_awaited_once()
```
- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3:** Update `start.py`: `import bot.services.db as db`; make handler `await` upsert + log_event with utm in its own kwarg.
- [ ] **Step 4:** run → PASS.
- [ ] **Step 5: Commit** `fix(start): persist utm + log it in its own column (was passed as detail)`

---

### Task 7: Startup/shutdown wiring in `__main__`

**Files:**
- Modify: `bot/__main__.py`

**Interfaces:**
- Consumes: `db.init_pool(settings.database_url)`, the pool's `close()`.
- Behavior: before `start_polling`, if `settings.database_url` is set, `await db.init_pool(settings.database_url)`; on shutdown close the pool. If `database_url` empty, log a warning and run without DB (events go to logs only) so local `/start` still works.

- [ ] **Step 1:** No unit test (integration-level). Manual check: `python -m bot` with no `DATABASE_URL` logs the warning and starts; with a valid one, creates tables.
- [ ] **Step 2:** Implement init in `main()` (guarded on `settings.database_url`), register shutdown to close pool.
- [ ] **Step 3:** Run `PYTHONPATH=. pytest -q` → all green (no regressions).
- [ ] **Step 4: Commit** `feat(app): init asyncpg pool + schema on startup, close on shutdown`

---

### Task 8: (Optional) integration test gated on DATABASE_URL

**Files:**
- Create: `tests/test_db_integration.py`

- [ ] **Step 1:** `pytestmark = pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="no DATABASE_URL")`. Real `init_pool`, `init_schema`, `append_event`, then `SELECT` the row back and assert columns. Use a throwaway/test DB.
- [ ] **Step 2:** Locally (with DB): `DATABASE_URL=... PYTHONPATH=. pytest tests/test_db_integration.py -v` → PASS; without DB → SKIPPED.
- [ ] **Step 3: Commit** `test(db): gated integration test against real Postgres`

---

## Self-Review notes

- **Spec coverage:** FED-239 requirements — events table + append (T2,T4), utm persistence/gap (T3,T6), log_event wired/TODO removed (T5), start bug fix (T6), deps/config swap (T1), test with mocked driver (T2–T6), optional integration (T8). ✓
- **Async migration:** `log_event` becomes async; only caller is `start.py` (T6) — no other call sites, so no missed awaits.
- **No live DB needed** for T1–T7 (mocked pool); DB only for T8 + runtime.
- **Open (not in this stage):** DB isolation choice (separate database vs schema) — needed for runtime/deploy, not for unit tests; confirm before FED-246.
