"""Integration test against a real Postgres. Explicit opt-in only.

Скипается, пока не задан RUN_DB_INTEGRATION=1 — чтобы тест НЕ запускался
автоматически просто из-за наличия DATABASE_URL в .env (он может указывать на
общий/боевой инстанс). Подключение идёт по `settings.dsn` (тот же, что в проде).

Запуск против ВЫДЕЛЕННОЙ базы ruslineup:
    RUN_DB_INTEGRATION=1 PYTHONPATH=. pytest tests/test_db_integration.py -v
Использует живую схему; за собой чистит созданные строки.
"""
import os

import pytest

import bot.services.db as db
from bot.config import settings

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_INTEGRATION"),
    reason="set RUN_DB_INTEGRATION=1 (against a dedicated ruslineup DB) to run",
)

_TEST_USER_ID = -999_000_001  # negative id never collides with real Telegram users


@pytest.fixture
async def pool():
    await db.init_pool(settings.dsn)
    try:
        # clean any leftovers from a previous run
        async with db.get_pool().acquire() as conn:
            await conn.execute("DELETE FROM events WHERE user_id = $1", _TEST_USER_ID)
            await conn.execute("DELETE FROM users WHERE user_id = $1", _TEST_USER_ID)
        yield db.get_pool()
    finally:
        async with db.get_pool().acquire() as conn:
            await conn.execute("DELETE FROM events WHERE user_id = $1", _TEST_USER_ID)
            await conn.execute("DELETE FROM users WHERE user_id = $1", _TEST_USER_ID)
        await db.close_pool()


async def test_append_event_roundtrip(pool):
    await db.append_event(
        user_id=_TEST_USER_ID,
        username="integration",
        utm_source="youtube",
        event="start",
        detail="tok_42",
    )
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT user_id, username, utm_source, event, detail "
            "FROM events WHERE user_id = $1",
            _TEST_USER_ID,
        )
    assert row["utm_source"] == "youtube"
    assert row["event"] == "start"
    assert row["detail"] == "tok_42"


async def test_upsert_keeps_first_touch_utm(pool):
    await db.upsert_user_utm(user_id=_TEST_USER_ID, username="integration", utm_source="youtube")
    # second touch with a different source must NOT overwrite
    await db.upsert_user_utm(user_id=_TEST_USER_ID, username="integration2", utm_source="instagram")
    assert await db.get_user_utm(_TEST_USER_ID) == "youtube"
