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


@pytest.mark.asyncio
async def test_send_event_swallows_post_error(monkeypatch):
    # сбой исходящего POST не должен пробрасываться (best-effort)
    monkeypatch.setattr(ga4, "settings", types.SimpleNamespace(
        ga4_measurement_id="G-X", ga4_api_secret="sec"))
    monkeypatch.setattr(ga4, "_post", AsyncMock(side_effect=RuntimeError("net")))
    await ga4.send_event("cid", "bot_start")  # не должно бросать
