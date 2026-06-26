# tests/test_llm.py
import types
import pytest
from unittest.mock import AsyncMock
import bot.services.llm as llm


def test_system_prompt_has_knowledge_and_env(monkeypatch):
    monkeypatch.setattr(llm, "settings", types.SimpleNamespace(
        board_12kw="ЦЕНА12", board_14kw="ЦЕНА14", seat_kit="СИД", battery_1="Б1",
        battery_2="Б2", partner_nick="@m", partner_discount="-5%",
        llm_api_key="", llm_model="gpt-4o"))
    monkeypatch.setattr(llm, "_knowledge_text", lambda: "ЭЛЕКТРОСЁРФ-ФАКТ")
    p = llm.build_system_prompt()
    assert "ЭЛЕКТРОСЁРФ-ФАКТ" in p
    assert "ЦЕНА12" in p and "-5%" in p
    assert "can_answer" in p  # инструкция про JSON-флаг


def _fake_client(content):
    msg = types.SimpleNamespace(content=content)
    resp = types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])
    completions = types.SimpleNamespace(create=AsyncMock(return_value=resp))
    return types.SimpleNamespace(chat=types.SimpleNamespace(completions=completions))


@pytest.mark.asyncio
async def test_ask_no_key_escalates(monkeypatch):
    monkeypatch.setattr(llm, "settings", types.SimpleNamespace(llm_api_key="", llm_model="gpt-4o"))
    answer, escalated = await llm.ask(1, "привет")
    assert answer == "" and escalated is True


@pytest.mark.asyncio
async def test_ask_parses_json(monkeypatch):
    monkeypatch.setattr(llm, "settings", types.SimpleNamespace(llm_api_key="sk-x", llm_model="gpt-4o"))
    monkeypatch.setattr(llm, "build_system_prompt", lambda: "SYS")
    client = _fake_client('{"answer": "Доски встают сразу", "can_answer": true}')
    monkeypatch.setattr(llm, "_client", lambda: client)
    llm._history.clear()
    answer, escalated = await llm.ask(7, "легко ли встать?")
    assert answer == "Доски встают сразу" and escalated is False
    sent = client.chat.completions.create.await_args.kwargs["messages"]
    assert sent[0] == {"role": "system", "content": "SYS"}
    assert sent[-1] == {"role": "user", "content": "легко ли встать?"}
    assert len(llm._history[7]) == 2  # вопрос+ответ в памяти


@pytest.mark.asyncio
async def test_ask_can_answer_false_escalates(monkeypatch):
    monkeypatch.setattr(llm, "settings", types.SimpleNamespace(llm_api_key="sk-x", llm_model="gpt-4o"))
    monkeypatch.setattr(llm, "build_system_prompt", lambda: "SYS")
    monkeypatch.setattr(llm, "_client", lambda: _fake_client('{"answer": "", "can_answer": false}'))
    llm._history.clear()
    answer, escalated = await llm.ask(8, "когда конец света?")
    assert escalated is True
