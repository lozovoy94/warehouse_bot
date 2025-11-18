from aiogram.fsm.state import State, StatesGroup


class StartStates(StatesGroup):
    waiting_name = State()


class OperationStates(StatesGroup):
    waiting_article = State()
    waiting_quantity = State()
    waiting_packing_type = State()
    waiting_other_task_type = State()
    waiting_finish = State()
