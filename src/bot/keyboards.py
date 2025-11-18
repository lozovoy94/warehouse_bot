from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from utils.texts import (
    BTN_START_SHIFT,
    BTN_END_SHIFT,
    BTN_FBS,
    BTN_PACKING,
    BTN_OTHER_TASKS,
    BTN_MY_REPORT,
    CB_FINISH_OPERATION,
    CB_CANCEL_OPERATION,
    OTHER_TASK_TYPES,
    PACKING_TYPES,
)


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_START_SHIFT), KeyboardButton(text=BTN_END_SHIFT)],
            [KeyboardButton(text=BTN_FBS), KeyboardButton(text=BTN_PACKING)],
            [KeyboardButton(text=BTN_OTHER_TASKS), KeyboardButton(text=BTN_MY_REPORT)],
        ],
        resize_keyboard=True,
    )


def operation_control_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Закончил", callback_data=CB_FINISH_OPERATION)],
            [InlineKeyboardButton(text="❌ Отменить", callback_data=CB_CANCEL_OPERATION)],
        ]
    )


def other_tasks_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=task, callback_data=f"other_task:{task}")]
        for task in OTHER_TASK_TYPES
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def packing_types_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=ptype, callback_data=f"pack_type:{ptype}")]
        for ptype in PACKING_TYPES
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)
