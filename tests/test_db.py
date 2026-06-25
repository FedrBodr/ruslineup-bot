import pytest
from unittest.mock import AsyncMock

import bot.services.db as db


class FakeConn:
    def __init__(self):
        self.execute = AsyncMock()
        self.fetchval = AsyncMock(return_value=None)


class FakePool:
    """Mimics asyncpg.Pool.acquire() as an async context manager."""

    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        conn = self._conn

        class _Acq:
            async def __aenter__(self_inner):
                return conn

            async def __aexit__(self_inner, *exc):
                return False

        return _Acq()


@pytest.mark.asyncio
async def test_append_event_inserts_row():
    conn = FakeConn()
    db.set_pool(FakePool(conn))
    await db.append_event(
        user_id=42, username="neo", utm_source="youtube", event="start", detail="tok_1"
    )
    assert conn.execute.await_count == 1
    args = conn.execute.await_args.args
    assert "INSERT INTO events" in args[0]
    assert args[1] is None  # ts → COALESCE(now())
    assert args[2:7] == (42, "neo", "youtube", "start", "tok_1")


@pytest.mark.asyncio
async def test_upsert_user_utm_first_touch():
    conn = FakeConn()
    db.set_pool(FakePool(conn))
    await db.upsert_user_utm(user_id=42, username="neo", utm_source="youtube")
    sql = conn.execute.await_args.args[0]
    assert "INSERT INTO users" in sql
    assert "ON CONFLICT" in sql
    assert "COALESCE" in sql  # keep first-touch utm


@pytest.mark.asyncio
async def test_get_user_utm_returns_value():
    conn = FakeConn()
    conn.fetchval = AsyncMock(return_value="instagram")
    db.set_pool(FakePool(conn))
    assert await db.get_user_utm(42) == "instagram"


@pytest.mark.asyncio
async def test_init_schema_creates_tables():
    conn = FakeConn()
    db.set_pool(FakePool(conn))
    await db.init_schema()
    ddl = " ".join(c.args[0] for c in conn.execute.await_args_list)
    assert "CREATE TABLE IF NOT EXISTS events" in ddl
    assert "CREATE TABLE IF NOT EXISTS users" in ddl


def test_get_pool_raises_when_unset():
    db.set_pool(None)
    with pytest.raises(RuntimeError):
        db.get_pool()
