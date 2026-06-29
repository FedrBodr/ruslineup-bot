# tests/test_metrika.py
import types
import pytest
from unittest.mock import AsyncMock
import bot.services.metrika as metrika


def test_build_csv():
    rows = [{"id": 1, "ts": None, "ym_cid": "y1", "target": "lead", "price": None}]
    csv_text = metrika._build_csv(rows)
    assert csv_text.splitlines()[0] == "ClientId,Target,DateTime,Price,Currency"
    assert "y1,lead," in csv_text


@pytest.mark.asyncio
async def test_upload_pending_marks(monkeypatch):
    monkeypatch.setattr(metrika, "settings", types.SimpleNamespace(
        ym_oauth_token="t", ym_counter_id="111"))
    monkeypatch.setattr(metrika.db, "fetch_pending_conversions",
                        AsyncMock(return_value=[{"id": 1, "ts": None, "ym_cid": "y", "target": "lead", "price": None}]))
    monkeypatch.setattr(metrika, "_upload", AsyncMock(return_value=True))
    mark = AsyncMock(); monkeypatch.setattr(metrika.db, "mark_conversions_uploaded", mark)
    n = await metrika.upload_pending()
    assert n == 1
    assert mark.await_args.args[0] == [1]


@pytest.mark.asyncio
async def test_upload_pending_noop_without_token(monkeypatch):
    monkeypatch.setattr(metrika, "settings", types.SimpleNamespace(ym_oauth_token="", ym_counter_id="111"))
    fetch = AsyncMock(); monkeypatch.setattr(metrika.db, "fetch_pending_conversions", fetch)
    assert await metrika.upload_pending() == 0
    fetch.assert_not_awaited()
