"""Тесты этапа 5 — промокоды (хендлер promo:get + db.insert_promo)."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import bot.handlers.promo as promo
import bot.services.db as db
from bot.services.promocode import generate_code


def _make_callback(user):
    """CallbackQuery-заглушка с замоканными message/answer."""
    message = SimpleNamespace(
        answer=AsyncMock(),
        edit_text=AsyncMock(),
        bot=SimpleNamespace(send_message=AsyncMock()),
    )
    return SimpleNamespace(
        data="promo:get",
        from_user=user,
        message=message,
        answer=AsyncMock(),
    )


def test_generate_code_stable():
    # детерминированно: один пользователь → всегда один и тот же код
    first = generate_code(777)
    second = generate_code(777)
    assert first == second
    assert first.startswith("RL_")


async def test_promo_get_shows_code_nick_and_discount(monkeypatch):
    user = SimpleNamespace(id=777, username="rider")
    monkeypatch.setattr(
        promo,
        "settings",
        SimpleNamespace(partner_nick="@bestmanager", partner_discount="10%"),
    )
    insert_mock = AsyncMock()
    log_mock = AsyncMock()
    monkeypatch.setattr(promo.db, "insert_promo", insert_mock)
    monkeypatch.setattr(promo, "log_event", log_mock)
    monkeypatch.setattr(promo.db, "get_user_cids", AsyncMock(return_value={"ga4_cid": "g", "ym_cid": "y"}))
    sent = AsyncMock(); monkeypatch.setattr(promo.ga4, "send_event", sent)
    enq = AsyncMock(); monkeypatch.setattr(promo.db, "enqueue_conversion", enq)

    callback = _make_callback(user)
    await promo.on_promo_get(callback)

    code = generate_code(777)

    # показан текст с кодом, ником партнёра и скидкой
    callback.message.edit_text.assert_awaited_once()
    text = callback.message.edit_text.call_args.args[0]
    assert code in text
    assert "@bestmanager" in text
    assert "10%" in text

    # код сохранён ровно один раз
    insert_mock.assert_awaited_once()
    kwargs = insert_mock.call_args.kwargs
    assert kwargs["code"] == code
    assert kwargs["user_id"] == 777
    assert kwargs["username"] == "rider"

    # событие залогировано
    log_mock.assert_awaited_once()
    assert log_mock.call_args.kwargs["event"] == "promo_issue"
    assert log_mock.call_args.kwargs["detail"] == code

    # GA4-событие.
    assert sent.await_args.args[1] == "promo_issue"

    # Метрика-конверсия.
    assert enq.await_args.kwargs["target"] == "promo"


async def test_promo_get_second_call_same_code(monkeypatch):
    """Повторный вызов выдаёт тот же код (идемпотентность)."""
    user = SimpleNamespace(id=42, username="u")
    monkeypatch.setattr(
        promo,
        "settings",
        SimpleNamespace(partner_nick="@m", partner_discount="5%"),
    )
    monkeypatch.setattr(promo.db, "insert_promo", AsyncMock())
    monkeypatch.setattr(promo, "log_event", AsyncMock())
    monkeypatch.setattr(promo.db, "get_user_cids",
                        AsyncMock(return_value={"ga4_cid": None, "ym_cid": None}))

    cb1 = _make_callback(user)
    cb2 = _make_callback(user)
    await promo.on_promo_get(cb1)
    await promo.on_promo_get(cb2)

    code1 = cb1.message.edit_text.call_args.args[0]
    code2 = cb2.message.edit_text.call_args.args[0]
    assert code1 == code2


async def test_promo_get_manager_button_prefills_code(monkeypatch):
    """Кнопка «Написать менеджеру» открывает чат с заготовленным текстом и кодом."""
    user = SimpleNamespace(id=777, username="rider")
    monkeypatch.setattr(
        promo,
        "settings",
        SimpleNamespace(partner_nick="@bestmanager", partner_discount="10%"),
    )
    monkeypatch.setattr(promo.db, "insert_promo", AsyncMock())
    monkeypatch.setattr(promo, "log_event", AsyncMock())
    monkeypatch.setattr(promo.db, "get_user_cids",
                        AsyncMock(return_value={"ga4_cid": None, "ym_cid": None}))

    callback = _make_callback(user)
    await promo.on_promo_get(callback)

    code = generate_code(777)
    markup = callback.message.edit_text.call_args.kwargs["reply_markup"]
    manager_btn = markup.inline_keyboard[0][0]
    assert manager_btn.url.startswith("https://t.me/bestmanager?text=")
    assert code in manager_btn.url  # код вшит в préfill (дефис не кодируется)
    assert "%" in manager_btn.url  # текст приветствия url-энкодится


async def test_insert_promo_noop_without_pool():
    db.set_pool(None)
    # не должно падать без пула
    await db.insert_promo(code="RL-AAAA", user_id=1, username="x")


async def test_insert_promo_executes_on_conflict():
    conn = SimpleNamespace(execute=AsyncMock())

    class _Acq:
        async def __aenter__(self):
            return conn

        async def __aexit__(self, *a):
            return False

    fake_pool = SimpleNamespace(acquire=lambda: _Acq())
    db.set_pool(fake_pool)
    try:
        await db.insert_promo(code="RL-BBBB", user_id=9, username="n")
    finally:
        db.set_pool(None)

    conn.execute.assert_awaited_once()
    sql = conn.execute.call_args.args[0]
    assert "INSERT INTO promo" in sql
    assert "ON CONFLICT (user_id) DO NOTHING" in sql
    assert conn.execute.call_args.args[1:] == ("RL-BBBB", 9, "n")


async def test_promo_analytics_failure_still_replies(monkeypatch):
    """Сбой аналитики (get_user_cids бросает) не мешает выдать код пользователю."""
    user = SimpleNamespace(id=777, username="rider")
    monkeypatch.setattr(promo, "settings",
                        SimpleNamespace(partner_nick="@m", partner_discount="5%"))
    monkeypatch.setattr(promo.db, "insert_promo", AsyncMock())
    monkeypatch.setattr(promo, "log_event", AsyncMock())
    monkeypatch.setattr(promo.db, "get_user_cids", AsyncMock(side_effect=RuntimeError("db down")))

    callback = _make_callback(user)
    await promo.on_promo_get(callback)  # не должно бросать

    callback.message.edit_text.assert_awaited_once()  # пользователь получил код
