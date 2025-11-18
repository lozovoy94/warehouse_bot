import logging
from datetime import date, datetime

from aiogram import Router, F, Dispatcher
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from ..config import Config
from ..sheets import sheets_client
from ..models.entities import Employee
from ..utils.datetime_utils import get_now_local, format_date_dmy, format_minutes_human
from ..utils.texts import (
    WELCOME_TEXT,
    ASK_NAME_TEXT,
    NOT_REGISTERED_TEXT,
    NO_OPEN_SHIFT_TEXT,
    OPERATION_ALREADY_ACTIVE_TEXT,
    BTN_START_SHIFT,
    BTN_END_SHIFT,
    BTN_FBS,
    BTN_PACKING,
    BTN_OTHER_TASKS,
    BTN_MY_REPORT,
    CB_FINISH_OPERATION,
    CB_CANCEL_OPERATION,
)
from .states import StartStates, OperationStates
from .keyboards import (
    main_menu_keyboard,
    operation_control_keyboard,
    other_tasks_keyboard,
    packing_types_keyboard,
)

logger = logging.getLogger(__name__)

router = Router()

_config: Config | None = None


def register_handlers(dp: Dispatcher, config: Config) -> None:
    global _config
    _config = config
    dp.include_router(router)


# ---------- Вспомогательные функции ----------

def _get_now():
    assert _config is not None
    return get_now_local(_config.timezone)


# ---------- /start и регистрация ----------

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    assert sheets_client is not None
    now = _get_now()
    emp = sheets_client.get_employee_by_telegram_id(message.from_user.id)

    if emp:
        await state.clear()
        await message.answer(
            f"{WELCOME_TEXT}\n\nРад тебя снова видеть, {emp.display_name} 👋",
            reply_markup=main_menu_keyboard(),
        )
        return

    await state.set_state(StartStates.waiting_name)
    await message.answer(
        f"{WELCOME_TEXT}\n\n{ASK_NAME_TEXT}",
        reply_markup=main_menu_keyboard(),
    )


@router.message(StartStates.waiting_name)
async def process_name(message: Message, state: FSMContext) -> None:
    assert sheets_client is not None
    now = _get_now()
    display_name = message.text.strip() if message.text else ""
    if not display_name:
        await message.answer("Имя не должно быть пустым. Напиши, как тебя называть.")
        return

    emp = sheets_client.register_employee(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        display_name=display_name,
        today=now.date(),
    )

    await state.clear()
    await message.answer(
        f"Отлично, {emp.display_name}! Ты зарегистрирован ✅\n"
        f"Теперь можешь пользоваться кнопками ниже.",
        reply_markup=main_menu_keyboard(),
    )


# ---------- Смены ----------

@router.message(F.text == BTN_START_SHIFT)
async def start_shift(message: Message) -> None:
    assert sheets_client is not None
    now = _get_now()
    emp = sheets_client.get_employee_by_telegram_id(message.from_user.id)
    if not emp:
        await message.answer(NOT_REGISTERED_TEXT)
        return

    if sheets_client.has_open_shift_for_today(emp.telegram_id, now.date()):
        await message.answer("Смена уже начата. Если хочешь завершить её — нажми «🔴 Закончить смену».")
        return

    try:
        sheets_client.start_shift(emp, now)
    except Exception:
        logger.exception("Error starting shift")
        await message.answer("Ошибка записи смены в таблицу. Сообщи руководителю.")
        return

    await message.answer(f"Смена начата в {now.strftime('%H:%M')} ✅")


@router.message(F.text == BTN_END_SHIFT)
async def end_shift(message: Message) -> None:
    assert sheets_client is not None
    now = _get_now()
    emp = sheets_client.get_employee_by_telegram_id(message.from_user.id)
    if not emp:
        await message.answer(NOT_REGISTERED_TEXT)
        return

    try:
        ok = sheets_client.end_shift(emp.telegram_id, now)
    except Exception:
        logger.exception("Error ending shift")
        await message.answer("Ошибка при завершении смены. Сообщи руководителю.")
        return

    if not ok:
        await message.answer("У тебя нет открытой смены.")
        return

    await message.answer(f"Смена завершена в {now.strftime('%H:%M')}.\nСпасибо за работу! 🙌")


# ---------- Операции: общие проверки ----------

async def _check_can_start_operation(message: Message, state: FSMContext) -> Employee | None:
    assert sheets_client is not None
    now = _get_now()
    emp = sheets_client.get_employee_by_telegram_id(message.from_user.id)
    if not emp:
        await message.answer(NOT_REGISTERED_TEXT)
        return None

    # проверка открытой смены
    if not sheets_client.has_open_shift_for_today(emp.telegram_id, now.date()):
        await message.answer(NO_OPEN_SHIFT_TEXT)
        return None

    # проверка активной операции
    current_state = await state.get_state()
    if current_state is not None:
        await message.answer(OPERATION_ALREADY_ACTIVE_TEXT)
        return None

    return emp


# ---------- Сборка FBS ----------

@router.message(F.text == BTN_FBS)
async def start_fbs_operation(message: Message, state: FSMContext) -> None:
    emp = await _check_can_start_operation(message, state)
    if not emp:
        return

    await state.set_state(OperationStates.waiting_article)
    await state.update_data(operation_type="Сборка FBS", employee_tg_id=emp.telegram_id)
    await message.answer("Отправь артикул товара (можно отсканировать штрихкод как текст).")


# ---------- Упаковка ----------

@router.message(F.text == BTN_PACKING)
async def start_packing_operation(message: Message, state: FSMContext) -> None:
    emp = await _check_can_start_operation(message, state)
    if not emp:
        return

    await state.set_state(OperationStates.waiting_article)
    await state.update_data(operation_type="Упаковка", employee_tg_id=emp.telegram_id)
    await message.answer("Отправь артикул товара для упаковки.")


# ---------- Обработка артикула (общая для FBS и Упаковки) ----------

@router.message(OperationStates.waiting_article)
async def process_article(message: Message, state: FSMContext) -> None:
    article = (message.text or "").strip()
    if not article:
        await message.answer("Артикул не должен быть пустым. Введи артикул.")
        return

    await state.update_data(article=article)
    await state.set_state(OperationStates.waiting_quantity)
    await message.answer("Сколько штук ты обрабатываешь по этому артикулу? Введи число.")


# ---------- Обработка количества (общая) ----------

@router.message(OperationStates.waiting_quantity)
async def process_quantity(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    try:
        qty = int(text)
        if qty <= 0:
            raise ValueError
    except Exception:
        await message.answer("Количество должно быть положительным числом. Попробуй ещё раз.")
        return

    now = _get_now()
    data = await state.get_data()
    article = data.get("article", "")
    op_type = data.get("operation_type", "Операция")

    await state.update_data(quantity=qty, start_time_iso=now.isoformat())
    await state.set_state(OperationStates.waiting_finish)

    await message.answer(
        f"Начал операцию «{op_type}» по артикулу <b>{article}</b>, количество <b>{qty}</b>.\n"
        f"Когда закончишь — нажми «✅ Закончил».",
        reply_markup=operation_control_keyboard(),
    )


# ---------- Прочие задачи ----------

@router.message(F.text == BTN_OTHER_TASKS)
async def start_other_task(message: Message, state: FSMContext) -> None:
    emp = await _check_can_start_operation(message, state)
    if not emp:
        return

    await state.set_state(OperationStates.waiting_other_task_type)
    await state.update_data(operation_type="Прочие задачи", employee_tg_id=emp.telegram_id)
    await message.answer("Выбери тип задачи:", reply_markup=other_tasks_keyboard())


@router.callback_query(OperationStates.waiting_other_task_type, F.data.startswith("other_task:"))
async def other_task_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    assert callback.message is not None
    task_type = callback.data.split(":", 1)[1]
    now = _get_now()

    await state.update_data(other_task_type=task_type, start_time_iso=now.isoformat())
    await state.set_state(OperationStates.waiting_finish)

    await callback.message.answer(
        f"Начал задачу: <b>{task_type}</b>.\n"
        f"Когда закончишь — нажми «✅ Закончил».",
        reply_markup=operation_control_keyboard(),
    )


# ---------- Завершение / отмена операции ----------

@router.callback_query(OperationStates.waiting_finish, F.data == CB_FINISH_OPERATION)
async def finish_operation(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    assert sheets_client is not None
    assert callback.message is not None

    now = _get_now()
    data = await state.get_data()
    op_type = data.get("operation_type", "Операция")
    article = data.get("article", "")
    quantity = data.get("quantity")
    start_iso = data.get("start_time_iso")
    other_task_type = data.get("other_task_type", "")
    employee_tg_id = data.get("employee_tg_id")

    if not start_iso or not employee_tg_id:
        await callback.message.answer("Не удалось определить начатую операцию. Попробуй начать заново.")
        await state.clear()
        return

    start_time = datetime.fromisoformat(start_iso)
    # приведение TZ (на всякий случай)
    now = now.replace(tzinfo=start_time.tzinfo)

    emp = sheets_client.get_employee_by_telegram_id(employee_tg_id)
    if not emp:
        await callback.message.answer("Сотрудник не найден. Нажми /start и попробуй ещё раз.")
        await state.clear()
        return

    date_str = format_date_dmy(start_time.date())
    extra = ""
    if op_type == "Прочие задачи":
        extra = other_task_type

    try:
        sheets_client.append_operation(
            employee=emp,
            op_type=op_type,
            date_str=date_str,
            article=article,
            quantity=quantity,
            time_start=start_time,
            time_end=now,
            extra=extra,
        )
    except Exception:
        logger.exception("Error appending operation")
        await callback.message.answer("Ошибка записи операции в таблицу. Сообщи руководителю.")
        await state.clear()
        return

    duration_min = int((now - start_time).total_seconds() // 60)
    if duration_min < 0:
        duration_min = 0

    if op_type == "Сборка FBS":
        text = (
            f"Готово! «Сборка FBS» по артикулу <b>{article}</b>: "
            f"{quantity} шт, потрачено {duration_min} мин."
        )
    elif op_type == "Упаковка":
        text = (
            f"Готово! «Упаковка» по артикулу <b>{article}</b>: "
            f"{quantity} шт, потрачено {duration_min} мин."
        )
    else:
        text = (
            f"Готово! Задача «{extra}» завершена, потрачено {duration_min} мин."
        )

    await callback.message.answer(text)
    await state.clear()


@router.callback_query(OperationStates.waiting_finish, F.data == CB_CANCEL_OPERATION)
async def cancel_operation(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    assert callback.message is not None
    await callback.message.answer("Операция отменена.")


# ---------- Мой отчёт за сегодня ----------

@router.message(F.text == BTN_MY_REPORT)
async def my_report_today(message: Message) -> None:
    assert sheets_client is not None
    now = _get_now()
    emp = sheets_client.get_employee_by_telegram_id(message.from_user.id)
    if not emp:
        await message.answer(NOT_REGISTERED_TEXT)
        return

    try:
        summary = sheets_client.build_employee_daily_summary(
            telegram_id=emp.telegram_id,
            day=now.date(),
            now_local=now,
        )
    except Exception:
        logger.exception("Error building daily summary")
        await message.answer("Ошибка получения отчёта. Сообщи руководителю.")
        return

    date_str = summary["date_str"]
    shift_ranges = summary["shift_ranges"]
    total_shift_minutes = summary["total_shift_minutes"]
    fbs_units = summary["fbs_units"]
    fbs_minutes = summary["fbs_minutes"]
    pack_units = summary["pack_units"]
    pack_minutes = summary["pack_minutes"]
    other_minutes = summary["other_minutes"]
    residue_minutes = summary["residue_minutes"]

    if not shift_ranges:
        await message.answer("На сегодня у тебя ещё нет смен. Нажми «🟢 Начать смену».")
        return

    shifts_str = "; ".join(shift_ranges)
    text_lines = [
        f"Отчёт за сегодня (<b>{date_str}</b>):",
        "",
        f"– Смены: {shifts_str}, всего {format_minutes_human(total_shift_minutes)}",
        f"– Сборка FBS: {fbs_units} шт, {format_minutes_human(fbs_minutes)}",
        f"– Упаковка: {pack_units} шт, {format_minutes_human(pack_minutes)}",
        f"– Прочие задачи: {format_minutes_human(other_minutes)}",
        f"– Непокрытое время: {format_minutes_human(residue_minutes)} "
        f"(перерывы, переходы, неотмеченные задачи)",
    ]

    await message.answer("\n".join(text_lines))


# ---------- /admin_summary ДЛЯ РУКОВОДИТЕЛЯ ----------

@router.message(Command("admin_summary"))
async def admin_summary(message: Message) -> None:
    """
    /admin_summary         -> по сегодняшнему дню
    /admin_summary 01.12.2025 -> по указанной дате
    """
    assert sheets_client is not None
    now = _get_now()
    parts = message.text.split(maxsplit=1)
    if len(parts) == 2:
        try:
            day = datetime.strptime(parts[1], "%d.%m.%Y").date()
        except Exception:
            await message.answer("Неверный формат даты. Используй ДД.ММ.ГГГГ.")
            return
    else:
        day = now.date()

    try:
        summary = sheets_client.build_admin_summary_for_date(day)
    except Exception:
        logger.exception("Error building admin summary")
        await message.answer("Ошибка при построении свода. Проверь таблицу или попробуй позже.")
        return

    date_str = summary["date_str"]
    employees = summary["employees"]
    if not employees:
        await message.answer(f"По дате {date_str} записей не найдено.")
        return

    lines = [f"Админ-свод за {date_str}:", ""]
    for emp in employees:
        name = emp["employee_name"] or f"TG {emp['telegram_id']}"
        shift_min = emp["shift_minutes"]
        fbs_units = emp["fbs_units"]
        fbs_min = emp["fbs_minutes"]
        pack_units = emp["pack_units"]
        pack_min = emp["pack_minutes"]
        other_min = emp["other_minutes"]

        lines.append(
            f"<b>{name}</b>:\n"
            f"  – Смены: {emp['shift_count']} шт, {format_minutes_human(shift_min)}\n"
            f"  – Сборка FBS: {fbs_units} шт, {format_minutes_human(fbs_min)}\n"
            f"  – Упаковка: {pack_units} шт, {format_minutes_human(pack_min)}\n"
            f"  – Прочие задачи: {format_minutes_human(other_min)}\n"
        )

    await message.answer("\n".join(lines))
