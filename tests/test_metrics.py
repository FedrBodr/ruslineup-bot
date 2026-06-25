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
    assert append.await_args.kwargs["user_id"] == 7


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
    monkeypatch.setattr(
        metrics.db, "append_event", AsyncMock(side_effect=RuntimeError("db down"))
    )
    monkeypatch.setattr(metrics.db, "get_user_utm", AsyncMock(return_value=None))
    user = SimpleNamespace(id=7, username="trinity")
    # a metrics failure must never break the user flow
    await metrics.log_event(user, event="start", utm="direct")
