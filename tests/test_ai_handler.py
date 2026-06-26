# tests/test_ai_handler.py
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock
import bot.handlers.ai as ai


def _msg(text="привет"):
    return SimpleNamespace(
        from_user=SimpleNamespace(id=7, username="u"),
        text=text,
        answer=AsyncMock(),
    )


def _settings():
    return SimpleNamespace(ai_daily_limit=20, partner_nick="@sportdoski")


@pytest.mark.asyncio
async def test_limit_reached_no_llm_call(monkeypatch):
    monkeypatch.setattr(ai, "settings", _settings())
    monkeypatch.setattr(ai.db, "count_today_event", AsyncMock(return_value=20))
    ask = AsyncMock()
    monkeypatch.setattr(ai, "ask", ask)
    monkeypatch.setattr(ai, "log_event", AsyncMock())
    m = _msg()
    await ai.on_free_text(m)
    ask.assert_not_awaited()
    m.answer.assert_awaited_once()  # сообщение про лимит


@pytest.mark.asyncio
async def test_answer_and_log(monkeypatch):
    monkeypatch.setattr(ai, "settings", _settings())
    monkeypatch.setattr(ai.db, "count_today_event", AsyncMock(return_value=0))
    monkeypatch.setattr(ai, "ask", AsyncMock(return_value=("Ответ", False)))
    log = AsyncMock()
    monkeypatch.setattr(ai, "log_event", log)
    m = _msg("легко встать?")
    await ai.on_free_text(m)
    m.answer.assert_awaited_once()
    assert m.answer.await_args.args[0] == "Ответ"
    assert log.await_args.kwargs["event"] == "ask_ai"
    assert log.await_args.kwargs["detail"] == "легко встать?"


@pytest.mark.asyncio
async def test_escalation_adds_manager_button(monkeypatch):
    monkeypatch.setattr(ai, "settings", _settings())
    monkeypatch.setattr(ai.db, "count_today_event", AsyncMock(return_value=0))
    monkeypatch.setattr(ai, "ask", AsyncMock(return_value=("", True)))
    log = AsyncMock()
    monkeypatch.setattr(ai, "log_event", log)
    m = _msg("вопрос не по теме")
    await ai.on_free_text(m)
    assert m.answer.await_args.kwargs.get("reply_markup") is not None
    assert log.await_args.kwargs["detail"].startswith("[escalate] ")
