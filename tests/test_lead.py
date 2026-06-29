import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock

import bot.handlers.lead as lead


def make_state(data=None):
    return SimpleNamespace(
        get_data=AsyncMock(return_value=dict(data or {})),
        update_data=AsyncMock(),
        set_state=AsyncMock(),
        clear=AsyncMock(),
    )


def make_callback(data):
    user = SimpleNamespace(id=7, username="trinity")
    message = SimpleNamespace(
        answer=AsyncMock(),
        edit_text=AsyncMock(),
        bot=SimpleNamespace(send_message=AsyncMock()),
    )
    return SimpleNamespace(data=data, from_user=user, message=message, answer=AsyncMock())


def make_message(text=None, contact=None):
    user = SimpleNamespace(id=7, username="trinity")
    return SimpleNamespace(
        text=text,
        contact=contact,
        from_user=user,
        answer=AsyncMock(),
        bot=SimpleNamespace(send_message=AsyncMock()),
    )


@pytest.mark.asyncio
async def test_entry_sets_type_and_asks_name():
    state = make_state()
    cb = make_callback("lead:testday")

    await lead.lead_entry(cb, state)

    # Тип заявки сохранён в FSM.
    assert state.update_data.await_args.kwargs["lead_type"] == "testday"
    # Перешли в состояние ожидания имени.
    state.set_state.assert_awaited_once_with(lead.LeadForm.waiting_name)
    # Для тест-дня показан вводный текст; цена не называется.
    sent = " ".join(c.args[0] for c in cb.message.answer.await_args_list)
    assert "Тест-день" in sent
    assert "уточняйте у менеджера" in sent


@pytest.mark.asyncio
async def test_entry_partner_order_no_testday_text():
    state = make_state()
    cb = make_callback("lead:partner_order")

    await lead.lead_entry(cb, state)

    assert state.update_data.await_args.kwargs["lead_type"] == "partner_order"
    sent = " ".join(c.args[0] for c in cb.message.answer.await_args_list)
    assert "Тест-день" not in sent


@pytest.mark.asyncio
async def test_contact_step_accepts_shared_contact():
    state = make_state({"lead_type": "testday", "name": "Нео", "city": "Москва"})
    contact = SimpleNamespace(phone_number="+79990001122")
    message = make_message(text=None, contact=contact)

    await lead.lead_contact(message, state)

    assert state.update_data.await_args.kwargs["contact"] == "+79990001122"
    state.set_state.assert_awaited_once_with(lead.LeadForm.waiting_comment)


@pytest.mark.asyncio
async def test_contact_step_accepts_typed_text():
    state = make_state({"lead_type": "testday", "name": "Нео", "city": "Москва"})
    message = make_message(text="+70001112233", contact=None)

    await lead.lead_contact(message, state)

    assert state.update_data.await_args.kwargs["contact"] == "+70001112233"


@pytest.mark.asyncio
async def test_finish_inserts_lead_notifies_admin_and_logs(monkeypatch):
    insert = AsyncMock()
    log = AsyncMock()
    monkeypatch.setattr(lead.db, "insert_lead", insert)
    monkeypatch.setattr(lead.db, "get_user_utm", AsyncMock(return_value="youtube"))
    monkeypatch.setattr(lead.db, "get_user_cids", AsyncMock(return_value={"ga4_cid": "g", "ym_cid": "y"}))
    monkeypatch.setattr(lead, "log_event", log)
    monkeypatch.setattr(lead, "settings", SimpleNamespace(admin_chat_id="999"))
    sent = AsyncMock(); monkeypatch.setattr(lead.ga4, "send_event", sent)
    enq = AsyncMock(); monkeypatch.setattr(lead.db, "enqueue_conversion", enq)

    state = make_state(
        {
            "lead_type": "testday",
            "name": "Нео",
            "city": "Москва",
            "contact": "+79990001122",
        }
    )
    message = make_message(text="хочу на выходных")

    await lead.lead_comment(message, state)

    # Заявка записана с собранными полями.
    kwargs = insert.await_args.kwargs
    assert kwargs["name"] == "Нео"
    assert kwargs["city"] == "Москва"
    assert kwargs["contact"] == "+79990001122"
    assert kwargs["lead_type"] == "testday"
    assert kwargs["comment"] == "хочу на выходных"
    assert kwargs["user_id"] == 7

    # Уведомление админа содержит тип заявки.
    message.bot.send_message.assert_awaited_once()
    admin_args = message.bot.send_message.await_args.args
    assert admin_args[0] == "999"
    assert "testday" in admin_args[1]

    # Событие метрики.
    assert log.await_args.kwargs["event"] == "lead_submit"
    assert log.await_args.kwargs["detail"] == "testday"

    # GA4-событие.
    assert sent.await_args.args[1] == "lead_submit"

    # Метрика-конверсия.
    assert enq.await_args.kwargs["target"] == "lead"
    assert enq.await_args.kwargs["ym_cid"] == "y"

    # Состояние очищено, пользователю подтверждение.
    state.clear.assert_awaited_once()
    message.answer.assert_awaited()


@pytest.mark.asyncio
async def test_finish_skip_comment(monkeypatch):
    insert = AsyncMock()
    monkeypatch.setattr(lead.db, "insert_lead", insert)
    monkeypatch.setattr(lead.db, "get_user_utm", AsyncMock(return_value=None))
    monkeypatch.setattr(lead, "log_event", AsyncMock())
    monkeypatch.setattr(lead, "settings", SimpleNamespace(admin_chat_id="999"))

    state = make_state(
        {
            "lead_type": "partner_order",
            "name": "Нео",
            "city": "Москва",
            "contact": "+79990001122",
        }
    )
    message = make_message(text=lead.SKIP_TEXT)

    await lead.lead_comment(message, state)

    assert insert.await_args.kwargs["comment"] == ""
