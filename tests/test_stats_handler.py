import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock

import bot.handlers.stats as h
from bot.services.stats import Stats


def _msg(user_id):
    return SimpleNamespace(
        from_user=SimpleNamespace(id=user_id, username="u"),
        answer=AsyncMock(),
    )


@pytest.mark.asyncio
async def test_stats_ignored_for_non_admin(monkeypatch):
    monkeypatch.setattr(h, "settings", SimpleNamespace(admin_chat_id="999"))
    monkeypatch.setattr(h, "get_stats", AsyncMock(return_value=Stats.empty()))
    m = _msg(123)  # не админ
    await h.cmd_stats(m)
    m.answer.assert_not_awaited()


@pytest.mark.asyncio
async def test_stats_shown_to_admin(monkeypatch):
    monkeypatch.setattr(h, "settings", SimpleNamespace(admin_chat_id="999"))
    s = Stats(starts_total=100, starts_today=5, starts_7d=40,
              starts_by_source=[("youtube", 60)], faq_by_topic=[], leads_total=25,
              leads_by_type=[("testday", 20)], promo_total=10, recent_leads=[])
    monkeypatch.setattr(h, "get_stats", AsyncMock(return_value=s))
    m = _msg(999)  # админ
    await h.cmd_stats(m)
    m.answer.assert_awaited_once()
    text = m.answer.await_args.args[0]
    assert "100" in text and "25" in text
