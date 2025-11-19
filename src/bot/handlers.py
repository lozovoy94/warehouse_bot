from __future__ import annotations

import logging

from aiogram import Dispatcher, F, Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from src.config import AppConfig
from src.sheets import get_sheets_client
from .keyboards import main_menu_keyboard

logger = logging.getLogger(__name__)

router = Router()


def register_handlers(dp: Dispatcher, config: AppConfig) -> None:
    """
    Регистрируем все хендлеры на переданный Dispatcher.
    Конфиг пока не используем внутри, но оставляем параметр
    на будущее (вдруг понадобится текст/фича от окружения).
    """
    dp.include_router(router)


# -------- общие утилиты --------


def _require_sheets():
    sc = get_sheets_client()
    if sc is None:
        # Если вдруг что-то пошло не так при старте — сразу говорим об этом.
        raise RuntimeError("Sheets client is not initialized")
    return sc


def _user_info(message: Message) -> tuple[int, str, str | None]:
    user = message.from_user
    user_id = user.id
    full_name = (user.full_name or "").strip() or "Без имени"
    username = user.username
    return user_id, full_name, username


# -------- команды --------


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
            "Сообщи, пожалуйста, руководителю."
        )
        return

    await message.answer(text)


@router.message(F.text == "🔴 Завершить смену")
async def handle_end_shift(message: Message) -> None:
    sc = _require_sheets()
    user_id, full_name, username = _user_info(message)  # full_name/username пока не нужны

    try:
        ok, text = sc.end_shift(user_id=user_id)
    except Exception:
        logger.exception("Failed to end shift for user %s", user_id)
        await message.answer(
            "Не получилось завершить смену — бот пока не настроен до конца. "
            "Сообщи, пожалуйста, руководителю."
        )
        return

    await message.answer(text)


@router.message(F.text == "➕ Добавить операцию")
async def handle_add_operation(message: Message) -> None:
    """
    Для простоты пока делаем максимально лёгкий вариант:
    сотрудник присылает в ответ одно сообщение вида:

    вид_операции; артикул; количество; минуты; комментарий

    Пример:
    FBS-сборка; 123-ABC; 5; 20; собирал заказ WB123

    Всё, что не сможет распарситься, улетит в комментарий.
    На будущее тут можно будет прикрутить полноценную FSM.
    """
    await message.answer(
        "Пришли одним сообщением данные об операции в формате:\n\n"
        "<вид_операции>; <артикул>; <количество>; <минуты>; <комментарий>\n\n"
        "Пример:\n"
        "FBS-сборка; 123-ABC; 5; 20; собирал заказ WB123",
    )


@router.message(
    F.text
    & ~F.text.in_({"🟢 Начать смену", "🔴 Завершить смену", "➕ Добавить операцию", "📊 Итог за сегодня"})
)
async def handle_operation_freeform(message: Message) -> None:
    """
    Сюда попадает текст после нажатия «Добавить операцию».
    Никакого состояния не ведём — если формат похож на нужный, пишем как операцию.
    Если нет — всё равно пишем, но многое попадёт в комментарий.
    """
    text = message.text or ""
    parts = [p.strip() for p in text.split(";")]

    op_type = parts[0] if len(parts) >= 1 and parts[0] else "Операция"
    sku = parts[1] if len(parts) >= 2 and parts[1] else None

    def _to_int(s: str | None) -> int | None:
        if not s:
            return None
        try:
            return int(s)
        except ValueError:
            return None

    qty = _to_int(parts[2] if len(parts) >= 3 else None)
    minutes_spent = _to_int(parts[3] if len(parts) >= 4 else None)

    comment_parts = []
    if len(parts) >= 5:
        comment_parts.append("; ".join(parts[4:]))
    # если не удалось распарсить количество/минуты — добавим в комментарий
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
        logger.exception("Failed to add operation for user %s", user_id)
        await message.answer(
            "Не получилось сохранить операцию — сообщи, пожалуйста, руководителю."
        )
        return

    await message.answer(resp_text, reply_markup=main_menu_keyboard())


@router.message(F.text == "📊 Итог за сегодня")
async def handle_today_summary(message: Message) -> None:
    sc = _require_sheets()
    user_id, full_name, username = _user_info(message)

    try:
        text = sc.get_today_summary(user_id=user_id)
    except Exception:
        logger.exception("Failed to build summary for user %s", user_id)
        await message.answer(
            "Не получилось собрать итог за сегодня — сообщи, пожалуйста, руководителю."
        )
        return

    await message.answer(text)
