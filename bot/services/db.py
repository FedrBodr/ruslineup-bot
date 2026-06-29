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


async def init_schema() -> None:
    """Create tables if they do not exist (idempotent)."""
    async with get_pool().acquire() as conn:
        await conn.execute(CREATE_EVENTS)
        await conn.execute(CREATE_USERS)
        await conn.execute(CREATE_LEADS)
        await conn.execute(CREATE_PROMO)
        await conn.execute(CREATE_TOKENS)
        await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS ga4_cid TEXT")
        await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS ym_cid TEXT")
        await conn.execute(CREATE_CONVERSIONS)


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


async def count_today_event(user_id: int, event: str) -> int:
    if _pool is None:
        return 0
    sql = (
        "SELECT count(*) FROM events "
        "WHERE user_id = $1 AND event = $2 AND ts::date = now()::date"
    )
    async with _pool.acquire() as conn:
        return await conn.fetchval(sql, user_id, event) or 0


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
