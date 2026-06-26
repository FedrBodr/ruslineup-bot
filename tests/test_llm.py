# tests/test_llm.py
import types
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
