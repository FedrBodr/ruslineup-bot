import types
from unittest.mock import AsyncMock

import bot.content.faq as content
import bot.handlers.faq as faq_mod
from bot.config import Settings


def _make_settings() -> Settings:
    return Settings(
        board_12kw="ЦЕНА-12КВТ",
        board_14kw="ЦЕНА-14КВТ",
        seat_kit="ЦЕНА-СИДЕНЬЕ",
        battery_1="ЦЕНА-БАТ1",
        battery_2="ЦЕНА-БАТ2",
        preorder_terms="УСЛОВИЯ-ПРЕДЗАКАЗА",
    )


def _make_callback(data: str):
    user = types.SimpleNamespace(id=777, username="rider")
    message = types.SimpleNamespace(
        answer=AsyncMock(),
        edit_text=AsyncMock(),
        bot=types.SimpleNamespace(send_message=AsyncMock()),
    )
    return types.SimpleNamespace(
        data=data,
        from_user=user,
        message=message,
        answer=AsyncMock(),
    )


def _edit_text_call(cb):
    args, kwargs = cb.message.edit_text.call_args
    text = args[0] if args else kwargs["text"]
    return text, kwargs["reply_markup"]


def _callback_datas(markup):
    return [b.callback_data for row in markup.inline_keyboard for b in row]


async def test_boards(monkeypatch):
    log = AsyncMock()
    monkeypatch.setattr(faq_mod, "log_event", log)
    monkeypatch.setattr(faq_mod, "settings", _make_settings())

    cb = _make_callback("faq:boards")
    await faq_mod.on_boards(cb)

    cb.message.edit_text.assert_awaited_once()
    text, markup = _edit_text_call(cb)
    assert "Электросёрф" in text
    assert "ЦЕНА-12КВТ" in text
    assert "ЦЕНА-14КВТ" in text
    assert "ЦЕНА-СИДЕНЬЕ" in text
    assert "ЦЕНА-БАТ1" in text
    assert "ЦЕНА-БАТ2" in text
    assert "Предзаказ" not in text  # предзаказ убран из раздела досок (добавим позже)

    datas = _callback_datas(markup)
    assert datas == ["lead:testday", "lead:partner_order", "promo:get", "menu:main"]

    log.assert_awaited_once()
    assert log.call_args.kwargs["event"] == "faq_click"
    assert log.call_args.kwargs["detail"] == "boards"


async def test_camps(monkeypatch):
    log = AsyncMock()
    monkeypatch.setattr(faq_mod, "log_event", log)
    monkeypatch.setattr(faq_mod, "settings", _make_settings())

    cb = _make_callback("faq:camps")
    await faq_mod.on_camps(cb)

    cb.message.edit_text.assert_awaited_once()
    text, markup = _edit_text_call(cb)
    assert "Шри-Ланка" in text

    datas = _callback_datas(markup)
    assert datas == ["faq:community", "lead:testday", "menu:main"]

    log.assert_awaited_once()
    assert log.call_args.kwargs["event"] == "faq_click"
    assert log.call_args.kwargs["detail"] == "camps"


async def test_community(monkeypatch):
    log = AsyncMock()
    monkeypatch.setattr(faq_mod, "log_event", log)
    monkeypatch.setattr(faq_mod, "settings", _make_settings())

    cb = _make_callback("faq:community")
    await faq_mod.on_community(cb)

    cb.message.edit_text.assert_awaited_once()
    text, markup = _edit_text_call(cb)
    assert "t.me/russian_lineup_misovoe" in text
    assert "instagram.com/fedrbodr" in text
    assert "linkedin.com/in/dmitry-fedorenko" in text
    assert "@sportdoski" in text

    datas = _callback_datas(markup)
    assert datas == ["lead:testday", "menu:main"]

    log.assert_awaited_once()
    assert log.call_args.kwargs["event"] == "faq_click"
    assert log.call_args.kwargs["detail"] == "community"


async def test_menu_main(monkeypatch):
    log = AsyncMock()
    monkeypatch.setattr(faq_mod, "log_event", log)

    cb = _make_callback("menu:main")
    await faq_mod.on_menu_main(cb)

    cb.message.edit_text.assert_awaited_once()
    _text, markup = _edit_text_call(cb)
    datas = _callback_datas(markup)
    # возвращаемся в главное меню (этап 1)
    assert "faq:boards" in datas
    assert "lead:testday" in datas
    assert "promo:get" in datas


def test_content_interpolates_settings():
    text = content.boards_text(_make_settings())
    assert "ЦЕНА-12КВТ" in text
    assert "{BOARD_12KW}" not in text
