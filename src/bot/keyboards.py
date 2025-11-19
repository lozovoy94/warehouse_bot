from __future__ import annotations

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="🟢 Начать смену"),
                KeyboardButton(text="🔴 Завершить смену"),
            ],
            [
                KeyboardButton(text="➕ Добавить операцию"),
                KeyboardButton(text="📊 Итог за сегодня"),
            ],
        ],
        resize_keyboard=True,
    )
