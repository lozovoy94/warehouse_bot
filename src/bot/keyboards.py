from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    """
    Главная клавиатура под полем ввода.
    """
    keyboard = [
        [
            KeyboardButton(text="🟢 Начать смену"),
            KeyboardButton(text="🔴 Завершить смену"),
        ],
        [
            KeyboardButton(text="➕ Добавить операцию"),
            KeyboardButton(text="📊 Итог за сегодня"),
        ],
    ]
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
    )


def operation_type_keyboard() -> ReplyKeyboardMarkup:
    """
    Клавиатура выбора типа операции.
    Можно дополнять/менять под реальные процессы.
    """
    keyboard = [
        [
            KeyboardButton(text="Сборка FBS"),
            KeyboardButton(text="Упаковка"),
        ],
        [
            KeyboardButton(text="Приёмка"),
            KeyboardButton(text="Маркировка"),
        ],
        [
            KeyboardButton(text="Другое"),
            KeyboardButton(text="Отмена"),
        ],
    ]
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def cancel_keyboard() -> ReplyKeyboardMarkup:
    """
    Универсальная клавиатура с одной кнопкой «Отмена».
    """
    keyboard = [
        [KeyboardButton(text="Отмена")],
    ]
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        one_time_keyboard=True,
    )
