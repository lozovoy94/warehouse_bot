# src/bot/handlers.py

from __future__ import annotations

from aiogram import Router, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from aiogram.utils.keyboard import ReplyKeyboardBuilder

from .. import sheets  # важно: импортируем модуль, а не переменную


router = Router(name="warehouse_bot")


# --- Вспомогательные функции -------------------------------------------------


def _get_sheets_client():
    """
    Единая точка доступа к Google Sheets клиенту.
    Если по какой-то причине он не инициализирован — вернём None,
    а хендлер сам решит, что ответить пользователю.
    """
    try:
        return sheets.get_sheets_client()
    except Exception:
        # сюда попадём, если глобальный клиент не успел инициализироваться
        return None


def _main_menu_kb():
    kb = ReplyKeyboardBuilder()
    kb.button(text="🟢 Начать смену")
    kb.button(text="🔴 Завершить смену")
    kb.button(text="➕ Добавить операцию")
    kb.button(text="📊 Итог за сегодня")
    kb.adjust(2, 2)
    return kb.as_markup(resize_keyboard=True)


# --- Хендлеры ----------------------------------------------------------------


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    """
    Приветствие + вывод главного меню.
    Раньше тут падало на assert sheets_client is not None.
    Теперь клиент берётся аккуратно через _get_sheets_client().
    """
    client = _get_sheets_client()
    if client is None:
        await message.answer(
            "Привет! 👋\n\n"
            "Не получается подключиться к Google Sheets. "
            "Попробуй ещё раз через пару минут. Если ошибка повторяется — напиши руководителю, "
            "что «бот не может подключиться к таблице»."
        )
        return

    # Сбрасываем возможное старое состояние
    await state.clear()

    await message.answer(
        "Привет! Я бот для учёта работы на складе.\n\n"
        "Через меня ты можешь:\n"
        "• запускать и завершать смену\n"
        "• фиксировать, что именно делал и сколько\n"
        "• смотреть краткий итог за сегодня\n\n"
        "Выбери действие с клавиатуры ниже 👇",
        reply_markup=_main_menu_kb(),
    )


@router.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext) -> None:
    """
    Принудительное возвращение в главное меню.
    """
    await state.clear()
    await message.answer("Главное меню 👇", reply_markup=_main_menu_kb())


@router.message(F.text == "🟢 Начать смену")
async def start_shift(message: Message, state: FSMContext) -> None:
    client = _get_sheets_client()
    if client is None:
        await message.answer(
            "Не удалось подключиться к таблице Google Sheets. "
            "Смена не зафиксирована. Попробуй ещё раз позже."
        )
        return

    user_id = message.from_user.id
    full_name = message.from_user.full_name

    try:
        # TODO: приведи к фактическому имени метода в SheetsClient
        client.log_shift_start(user_id=user_id, user_name=full_name)
    except AttributeError:
        await message.answer(
            "Не получилось зафиксировать начало смены — бот пока не настроен до конца. "
            "Сообщи, пожалуйста, руководителю."
        )
        return

    await message.answer(
        "Смена запущена ✅\n\n"
        "Когда закончишь работу — нажми «🔴 Завершить смену».",
        reply_markup=_main_menu_kb(),
    )


@router.message(F.text == "🔴 Завершить смену")
async def stop_shift(message: Message, state: FSMContext) -> None:
    client = _get_sheets_client()
    if client is None:
        await message.answer(
            "Не удалось подключиться к таблице Google Sheets. "
            "Конец смены не зафиксирован. Попробуй ещё раз позже."
        )
        return

    user_id = message.from_user.id

    try:
        # TODO: приведи к фактическому имени метода
        client.log_shift_end(user_id=user_id)
    except AttributeError:
        await message.answer(
            "Не получилось зафиксировать конец смены — бот пока не настроен до конца. "
            "Сообщи, пожалуйста, руководителю."
        )
        return

    await message.answer(
        "Смена завершена ✅\n\n"
        "Спасибо за работу! Если нужно что-то дописать — можно запустить новую смену.",
        reply_markup=_main_menu_kb(),
    )


@router.message(F.text == "➕ Добавить операцию")
async def add_operation_entry(message: Message, state: FSMContext) -> None:
    """
    Заготовка хендлера для добавления записи по операции (сборка/упаковка и т.п.).
    Здесь позже можно сделать FSM-диалог. Пока заглушка.
    """
    await message.answer(
        "Добавление операций пока не настроено до конца 🛠\n\n"
        "Но бот уже умеет фиксировать начало и конец смены. "
        "Когда донастроим операции — здесь появится простой диалог для ввода данных.",
        reply_markup=_main_menu_kb(),
    )


@router.message(F.text == "📊 Итог за сегодня")
async def today_summary(message: Message, state: FSMContext) -> None:
    client = _get_sheets_client()
    if client is None:
        await message.answer(
            "Не получилось подключиться к таблице Google Sheets. "
            "Сводка за сегодня недоступна. Попробуй позже."
        )
        return

    user_id = message.from_user.id

    try:
        # TODO: приведи к фактическому имени метода
        summary = client.get_today_summary(user_id=user_id)
    except AttributeError:
        await message.answer(
            "Сводка за сегодня пока не настроена 🛠\n"
            "Основной функционал — учёт смен — уже работает."
        )
        return

    await message.answer(
        f"Твоя сводка за сегодня:\n\n{summary}",
        reply_markup=_main_menu_kb(),
    )


@router.message()
async def fallback(message: Message) -> None:
    """
    Общий хендлер на всё остальное — чтобы не было ощущения «бот молчит».
    """
    await message.answer(
        "Пока я понимаю только команды с кнопок 👇\n\n"
        "Если что-то не работает — начни с /start.",
        reply_markup=_main_menu_kb(),
    )


# --- Регистрация в диспетчере ------------------------------------------------


def register_handlers(dp, config) -> None:
    """
    Вызывается из main.py: register_handlers(dp, config)
    config сейчас не используем, но принимаем, чтобы не было TypeError.
    """
    dp.include_router(router)
