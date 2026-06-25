import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock

import bot.handlers.start as start


@pytest.mark.asyncio
async def test_cmd_start_logs_utm_and_upserts(monkeypatch):
    log = AsyncMock()
    upsert = AsyncMock()
    monkeypatch.setattr(start, "log_event", log)
    monkeypatch.setattr(start.db, "upsert_user_utm", upsert)
    user = SimpleNamespace(id=7, username="trinity")
    message = SimpleNamespace(from_user=user, answer=AsyncMock())
    command = SimpleNamespace(args="youtube")

    await start.cmd_start(message, command)

    assert upsert.await_args.kwargs["utm_source"] == "youtube"
    assert upsert.await_args.kwargs["user_id"] == 7
    assert log.await_args.kwargs["utm"] == "youtube"
    assert log.await_args.kwargs["event"] == "start"
    message.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_cmd_start_defaults_to_direct(monkeypatch):
    log = AsyncMock()
    upsert = AsyncMock()
    monkeypatch.setattr(start, "log_event", log)
    monkeypatch.setattr(start.db, "upsert_user_utm", upsert)
    user = SimpleNamespace(id=7, username="trinity")
    message = SimpleNamespace(from_user=user, answer=AsyncMock())
    command = SimpleNamespace(args=None)

    await start.cmd_start(message, command)

    assert upsert.await_args.kwargs["utm_source"] == "direct"
    assert log.await_args.kwargs["utm"] == "direct"
