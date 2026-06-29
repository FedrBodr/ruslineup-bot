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
    monkeypatch.setattr(start.db, "set_user_cids", AsyncMock())
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
    monkeypatch.setattr(start.db, "set_user_cids", AsyncMock())
    user = SimpleNamespace(id=7, username="trinity")
    message = SimpleNamespace(from_user=user, answer=AsyncMock())
    command = SimpleNamespace(args=None)

    await start.cmd_start(message, command)

    assert upsert.await_args.kwargs["utm_source"] == "direct"
    assert log.await_args.kwargs["utm"] == "direct"


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
