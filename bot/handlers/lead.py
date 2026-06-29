"""FSM-диалог сбора заявок (этап 4).

Пользователь жмёт одну из кнопок lead:* → бот по шагам спрашивает имя, город,
контакт и (опционально) комментарий, затем пишет заявку в Postgres, уведомляет
админа и логирует событие. Тип заявки фиксируется входным callback и хранится в
состоянии FSM.
"""
import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

import bot.services.db as db
import bot.services.ga4 as ga4
from bot.config import settings
from bot.services.metrics import log_event

router = Router()
logger = logging.getLogger("lead")


class LeadForm(StatesGroup):
    waiting_name = State()
    waiting_city = State()
    waiting_contact = State()
    waiting_comment = State()


# callback_data → значение в leads.type. preorder добавим отдельной темой позже.
LEAD_TYPES = {
    "lead:testday": "testday",
    "lead:partner_order": "partner_order",
}

# Человекочитаемые ярлыки для уведомления админа (raw-тип тоже подставляем).
TYPE_LABELS = {
    "testday": "Тест-день",
    "partner_order": "Заказ у партнёра",
}

# v1: фиксированной цены нет — отправляем к менеджеру, сумму не называем.
TESTDAY_TEXT = (
    "Тест-день: привозим доски + генератор. Катаемся, заряжаемся, обедаем "
    "и снова катаемся 🏄 Стоимость — уточняйте у менеджера, забронируем дату под тебя."
)

ASK_NAME = "Как тебя зовут?"
ASK_CITY = "Из какого ты города?"
ASK_CONTACT = (
    "Оставь контакт для связи: нажми кнопку ниже или напиши телефон/ник вручную."
)
SKIP_TEXT = "Пропустить"
ASK_COMMENT = (
    "Хочешь что-то добавить? Напиши комментарий или нажми «Пропустить»."
)
CONFIRM = "Спасибо! Заявка принята — менеджер свяжется с тобой в ближайшее время 🤙"


def _contact_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Поделиться контактом", request_contact=True)]
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def _skip_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=SKIP_TEXT)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


@router.callback_query(F.data.startswith("lead:"))
async def lead_entry(callback: CallbackQuery, state: FSMContext) -> None:
    lead_type = LEAD_TYPES.get(callback.data)
    if lead_type is None:
        await callback.answer()
        return
    await state.update_data(lead_type=lead_type)
    await callback.answer()
    if lead_type == "testday":
        await callback.message.answer(TESTDAY_TEXT)
    await callback.message.answer(ASK_NAME)
    await state.set_state(LeadForm.waiting_name)


@router.message(LeadForm.waiting_name)
async def lead_name(message: Message, state: FSMContext) -> None:
    await state.update_data(name=(message.text or "").strip())
    await message.answer(ASK_CITY)
    await state.set_state(LeadForm.waiting_city)


@router.message(LeadForm.waiting_city)
async def lead_city(message: Message, state: FSMContext) -> None:
    await state.update_data(city=(message.text or "").strip())
    await message.answer(ASK_CONTACT, reply_markup=_contact_kb())
    await state.set_state(LeadForm.waiting_contact)


@router.message(LeadForm.waiting_contact)
async def lead_contact(message: Message, state: FSMContext) -> None:
    # Контакт можно прислать кнопкой (request_contact) или ввести текстом.
    if message.contact is not None:
        contact = message.contact.phone_number
    else:
        contact = (message.text or "").strip()
    await state.update_data(contact=contact)
    await message.answer(ASK_COMMENT, reply_markup=_skip_kb())
    await state.set_state(LeadForm.waiting_comment)


@router.message(LeadForm.waiting_comment)
async def lead_comment(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    comment = "" if text == SKIP_TEXT else text
    await _finish(message, state, comment)


async def _finish(message: Message, state: FSMContext, comment: str) -> None:
    data = await state.get_data()
    lead_type = data.get("lead_type", "")
    name = data.get("name", "")
    city = data.get("city", "")
    contact = data.get("contact", "")
    user = message.from_user

    utm = await db.get_user_utm(user.id) or ""

    await db.insert_lead(
        user_id=user.id,
        username=user.username,
        name=name,
        city=city,
        contact=contact,
        lead_type=lead_type,
        comment=comment,
        utm_source=utm,
    )

    label = TYPE_LABELS.get(lead_type, lead_type)
    summary = (
        f"🆕 Новая заявка: {label} ({lead_type})\n"
        f"Имя: {name}\n"
        f"Город: {city}\n"
        f"Контакт: {contact}\n"
        f"Комментарий: {comment or '—'}\n"
        f"От: @{user.username} (id {user.id})"
    )
    await message.bot.send_message(settings.admin_chat_id, summary)

    await log_event(user, event="lead_submit", detail=lead_type)

    await state.clear()
    await message.answer(CONFIRM, reply_markup=ReplyKeyboardRemove())

    # Аналитика — best-effort, ПОСЛЕ ответа пользователю.
    try:
        cids = await db.get_user_cids(user.id)
        if cids.get("ga4_cid"):
            await ga4.send_event(cids["ga4_cid"], "lead_submit", {"type": lead_type})
        if cids.get("ym_cid"):
            await db.enqueue_conversion(user_id=user.id, ym_cid=cids["ym_cid"], target="lead")
    except Exception:
        logger.warning("lead analytics failed (best-effort)", exc_info=True)
