"""PostgreSQL data layer (asyncpg). Source of truth for метрики, заявки и промокоды.

The pool is held module-level and injected via `set_pool` so unit tests can
substitute a fake pool with no live database. All write helpers are no-ops when
the pool is unset, so the bot still runs locally without a DATABASE_URL
(events fall back to logs only — see `metrics.log_event`).
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

import asyncpg

_pool: Optional[asyncpg.Pool] = None


def set_pool(pool: Optional[asyncpg.Pool]) -> None:
    global _pool
    _pool = pool


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("DB pool is not initialised — call init_pool() at startup")
    return _pool


CREATE_EVENTS = """
CREATE TABLE IF NOT EXISTS events (
    id          BIGSERIAL PRIMARY KEY,
    ts          TIMESTAMPTZ NOT NULL DEFAULT now(),
    user_id     BIGINT NOT NULL,
    username    TEXT,
    utm_source  TEXT,
    event       TEXT NOT NULL,
    detail      TEXT NOT NULL DEFAULT ''
)
"""

CREATE_USERS = """
CREATE TABLE IF NOT EXISTS users (
    user_id     BIGINT PRIMARY KEY,
    username    TEXT,
    utm_source  TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""

CREATE_LEADS = """
CREATE TABLE IF NOT EXISTS leads (
    id          BIGSERIAL PRIMARY KEY,
    ts          TIMESTAMPTZ NOT NULL DEFAULT now(),
    user_id     BIGINT,
    username    TEXT,
    name        TEXT,
    city        TEXT,
    contact     TEXT,
    type        TEXT,
    comment     TEXT,
    utm_source  TEXT,
    status      TEXT DEFAULT 'new'
)
"""

CREATE_PROMO = """
CREATE TABLE IF NOT EXISTS promo (
    code        TEXT UNIQUE,
    user_id     BIGINT PRIMARY KEY,
    username    TEXT,
    issued_at   TIMESTAMPTZ DEFAULT now(),
    status      TEXT DEFAULT 'issued',
    sale_amount NUMERIC
)
"""


async def init_schema() -> None:
    """Create tables if they do not exist (idempotent)."""
    async with get_pool().acquire() as conn:
        await conn.execute(CREATE_EVENTS)
        await conn.execute(CREATE_USERS)
        await conn.execute(CREATE_LEADS)
        await conn.execute(CREATE_PROMO)


async def init_pool(dsn: str) -> None:
    """Create the asyncpg pool and ensure the schema exists."""
    set_pool(await asyncpg.create_pool(dsn))
    await init_schema()


async def close_pool() -> None:
    if _pool is not None:
        await _pool.close()
        set_pool(None)


async def append_event(
    *,
    user_id: int,
    username: Optional[str],
    utm_source: str,
    event: str,
    detail: str = "",
    ts: Optional[datetime] = None,
) -> None:
    """Insert one row into `events`. No-op if the pool is unset."""
    if _pool is None:
        return
    sql = (
        "INSERT INTO events(ts, user_id, username, utm_source, event, detail) "
        "VALUES(COALESCE($1, now()), $2, $3, $4, $5, $6)"
    )
    async with _pool.acquire() as conn:
        await conn.execute(sql, ts, user_id, username, utm_source, event, detail)


async def upsert_user_utm(*, user_id: int, username: Optional[str], utm_source: str) -> None:
    """Record a user and their utm_source, keeping the first-touch value."""
    if _pool is None:
        return
    sql = (
        "INSERT INTO users(user_id, username, utm_source) VALUES($1, $2, $3) "
        "ON CONFLICT (user_id) DO UPDATE SET "
        "username = EXCLUDED.username, "
        "utm_source = COALESCE(users.utm_source, EXCLUDED.utm_source)"
    )
    async with _pool.acquire() as conn:
        await conn.execute(sql, user_id, username, utm_source)


async def get_user_utm(user_id: int) -> Optional[str]:
    """Return the stored utm_source for a user, or None."""
    if _pool is None:
        return None
    sql = "SELECT utm_source FROM users WHERE user_id = $1"
    async with _pool.acquire() as conn:
        return await conn.fetchval(sql, user_id)


async def insert_lead(
    *,
    user_id: int,
    username: Optional[str],
    name: str,
    city: str,
    contact: str,
    lead_type: str,
    comment: str,
    utm_source: str = "",
) -> None:
    """Insert one row into `leads`. No-op if the pool is unset."""
    if _pool is None:
        return
    sql = (
        "INSERT INTO leads(user_id, username, name, city, contact, type, comment, utm_source) "
        "VALUES($1, $2, $3, $4, $5, $6, $7, $8)"
    )
    async with _pool.acquire() as conn:
        await conn.execute(
            sql, user_id, username, name, city, contact, lead_type, comment, utm_source
        )


async def insert_promo(*, code: str, user_id: int, username: Optional[str]) -> None:
    """Сохранить промокод пользователя один раз. No-op если пул не задан."""
    if _pool is None:
        return
    sql = (
        "INSERT INTO promo(code, user_id, username) VALUES($1, $2, $3) "
        "ON CONFLICT (user_id) DO NOTHING"
    )
    async with _pool.acquire() as conn:
        await conn.execute(sql, code, user_id, username)


async def get_promo_code(user_id: int) -> Optional[str]:
    """Вернуть сохранённый промокод пользователя, либо None."""
    if _pool is None:
        return None
    sql = "SELECT code FROM promo WHERE user_id = $1"
    async with _pool.acquire() as conn:
        return await conn.fetchval(sql, user_id)
