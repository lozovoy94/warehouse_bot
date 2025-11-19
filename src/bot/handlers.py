from __future__ import annotations

import logging

from aiogram import Dispatcher, F, Router
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from src.config import AppConfig
from src.sheets import get_sheets_client
from .keyboards import main_menu_keyboard, operation_type_keyboard, cancel_keyboard

logger = logging.getLogger(__name__)

router = Router()


def register_handlers(dp: Dispatcher, config: AppConfig) -> None:
    """
    Регистрируем все хендлеры на переданный Dispatcher.
    Конфиг пока не используем, но оставляем на будущее.
    """
    dp.include_router(router)


# -------- FSM для добавления операции --------


class OperationForm(StatesGroup):
    operation_type = State()
    sku = State()
    qty = State()
    minutes = State()
    comment = State()


# -------- общие утилиты --------


def _require_sheets():
    sc = get_sheets_client()
    if sc is None:
        raise RuntimeError("Sheets client is not initialized")
    return sc


def _user_info(message: Message) -> tuple[int, str, str | None]:
    user = message.from_user
    user_id = user.id
    full_name = (user.full_name or "").strip() or "Без имени"
    username = user.username
    return user_id, full_name, username


def _safe_int(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


# -------- старт и смены --------


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(
        "Привет! Я бот для учёта работы на складе.\n\n"
        "Через меня ты можешь:\n"
        "• запускать и завершать смену\n"
        "• фиксировать, что именно делал и сколько\n"
        "• смотреть краткий итог за сегодня\n\n"
        "Выбери действие с клавиатуры ниже 👇",
        reply_markup=main_menu_keyboard(),
    )


@router.message(F.text == "🟢 Начать смену")
async def handle_start_shift(message: Message) -> None:
    sc = _require_sheets()
    user_id, full_name, username = _user_info(message)

    try:
        ok, text = sc.start_shift(user_id=user_id, full_name=full_name, username=username)
    except Exception:
        logger.exception("Failed to start shift for user %s", user_id)
        await message.answer(
            "Не получилось зафиксировать начало смены — бот пока не настроен до конца. "
            "Сообщи, пожалуйста, руководителю.",
            reply_markup=main_menu_keyboard(),
        )
        return

    await message.answer(text, reply_markup=main_menu_keyboard())


@router.message(F.text == "🔴 Завершить смену")
async def handle_end_shift(message: Message) -> None:
    sc = _require_sheets()
    user_id, full_name, username = _user_info(message)

    try:
        ok, text = sc.end_shift(user_id=user_id)
    except Exception:
        logger.exception("Failed to end shift for user %s", user_id)
        await message.answer(
            "Не получилось завершить смену — бот пока не настроен до конца. "
            "Сообщи, пожалуйста, руководителю.",
            reply_markup=main_menu_keyboard(),
        )
        return

    await message.answer(text, reply_markup=main_menu_keyboard())


# -------- добавление операции: пошаговый диалог --------


@router.message(F.text == "➕ Добавить операцию")
async def handle_add_operation(message: Message, state: FSMContext) -> None:
    """
    Старт диалога добавления операции.
    """
    await state.clear()

    await state.set_state(OperationForm.operation_type)
    await message.answer(
        "Давай запишем, что ты делал.\n\n"
        "1️⃣ Сначала выбери, какой у тебя был вид работы:",
        reply_markup=operation_type_keyboard(),
    )


@router.message(OperationForm.operation_type)
async def op_step_operation_type(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()

    if text == "Отмена":
        await state.clear()
        await message.answer(
            "Ок, ничего не записываю. Возвращаюсь в главное меню.",
            reply_markup=main_menu_keyboard(),
        )
        return

    await state.update_data(operation_type=text)

    await state.set_state(OperationForm.sku)
    await message.answer(
        "2️⃣ Напиши артикул товара.\n"
        "Если артикул не нужен (например, общая работа по зоне) — напиши «-».",
        reply_markup=cancel_keyboard(),
    )


@router.message(OperationForm.sku)
async def op_step_sku(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()

    if text == "Отмена":
        await state.clear()
        await message.answer(
            "Ок, отменил добавление операции. Главное меню ниже 👇",
            reply_markup=main_menu_keyboard(),
        )
        return

    sku = None if text == "-" else text
    await state.update_data(sku=sku)

    await state.set_state(OperationForm.qty)
    await message.answer(
        "3️⃣ Сколько единиц / заказов ты сделал?\n"
        "Если поштучно не считаешь — напиши 0.",
        reply_markup=cancel_keyboard(),
    )


@router.message(OperationForm.qty)
async def op_step_qty(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()

    if text == "Отмена":
        await state.clear()
        await message.answer(
            "Ок, отменил добавление операции. Главное меню ниже 👇",
            reply_markup=main_menu_keyboard(),
        )
        return

    qty = _safe_int(text)
    await state.update_data(qty=qty)

    await state.set_state(OperationForm.minutes)
    await message.answer(
        "4️⃣ Сколько минут у тебя ушло на эту операцию? "
        "Если не уверен — напиши примерно.",
        reply_markup=cancel_keyboard(),
    )


@router.message(OperationForm.minutes)
async def op_step_minutes(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()

    if text == "Отмена":
        await state.clear()
        await message.answer(
            "Ок, отменил добавление операции. Главное меню ниже 👇",
            reply_markup=main_menu_keyboard(),
        )
        return

    minutes = _safe_int(text)
    await state.update_data(minutes=minutes)

    await state.set_state(OperationForm.comment)
    await message.answer(
        "5️⃣ Если хочешь, добавь комментарий (например, номер заказа). "
        "Если комментарий не нужен — напиши «-».",
        reply_markup=cancel_keyboard(),
    )


@router.message(OperationForm.comment)
async def op_step_comment(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()

    if text == "Отмена":
        await state.clear()
        await message.answer(
            "Ок, отменил добавление операции. Главное меню ниже 👇",
            reply_markup=main_menu_keyboard(),
        )
        return

    comment = None if text == "-" else text

    data = await state.get_data()
    await state.clear()

    sc = _require_sheets()
    user_id, full_name, username = _user_info(message)

    try:
        ok, resp_text = sc.add_operation(
            user_id=user_id,
            full_name=full_name,
            username=username,
            operation_type=data.get("operation_type") or "Операция",
            sku=data.get("sku"),
            qty=data.get("qty"),
            minutes_spent=data.get("minutes"),
            comment=comment,
        )
    except Exception:
        logger.exception("Failed to add operation for user %s", user_id)
        await message.answer(
            "Не получилось сохранить операцию — сообщи, пожалуйста, руководителю.",
            reply_markup=main_menu_keyboard(),
        )
        return

    await message.answer(resp_text, reply_markup=main_menu_keyboard())


# -------- быстрый ввод одной строкой (для продвинутых) --------


@router.message(
    StateFilter(None),
    F.text
    & ~F.text.in_(
        {
            "🟢 Начать смену",
            "🔴 Завершить смену",
            "➕ Добавить операцию",
            "📊 Итог за сегодня",
            "Отмена",
        }
    ),
)
async def handle_operation_freeform(message: Message) -> None:
    """
    Если пользователь сам прислал строку вида:
    вид_операции; артикул; количество; минуты; комментарий
    — попробуем аккуратно распарсить и записать как операцию.
    """
    text = message.text or ""
    parts = [p.strip() for p in text.split(";")]

    if len(parts) < 2:
        # Явно не похоже на нашу схему — просто молча игнорируем,
        # чтобы не спамить работника, или в будущем можно показать подсказку.
        return

    op_type = parts[0] or "Операция"
    sku = parts[1] or None
    qty = _safe_int(parts[2] if len(parts) >= 3 else None)
    minutes_spent = _safe_int(parts[3] if len(parts) >= 4 else None)

    comment_parts: list[str] = []
    if len(parts) >= 5:
        comment_parts.append("; ".join(parts[4:]))

    if qty is None and len(parts) >= 3:
        comment_parts.append(f"Не удалось распознать количество из «{parts[2]}»")
    if minutes_spent is None and len(parts) >= 4:
        comment_parts.append(f"Не удалось распознать минуты из «{parts[3]}»")

    comment = " | ".join(comment_parts) if comment_parts else None

    sc = _require_sheets()
    user_id, full_name, username = _user_info(message)

    try:
        ok, resp_text = sc.add_operation(
            user_id=user_id,
            full_name=full_name,
            username=username,
            operation_type=op_type,
            sku=sku,
            qty=qty,
            minutes_spent=minutes_spent,
            comment=comment,
        )
    except Exception:
        logger.exception("Failed to add operation (freeform) for user %s", user_id)
        await message.answer(
            "Не получилось сохранить операцию — сообщи, пожалуйста, руководителю.",
            reply_markup=main_menu_keyboard(),
        )
        return

    await message.answer(resp_text, reply_markup=main_menu_keyboard())


# -------- итог за сегодня --------


@router.message(F.text == "📊 Итог за сегодня")
async def handle_today_summary(message: Message) -> None:
    sc = _require_sheets()
    user_id, full_name, username = _user_info(message)

    try:
        text = sc.get_today_summary(user_id=user_id)
    except Exception:
        logger.exception("Failed to build summary for user %s", user_id)
        await message.answer(
            "Не получилось собрать итог за сегодня — сообщи, пожалуйста, руководителю.",
            reply_markup=main_menu_keyboard(),
        )
        return

    await message.answer(text, reply_markup=main_menu_keyboard())
