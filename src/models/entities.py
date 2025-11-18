from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Employee:
    internal_id: int
    telegram_id: int
    username: Optional[str]
    display_name: str
    registered_at: str  # строка даты (ДД.ММ.ГГГГ)


@dataclass
class Shift:
    date_str: str
    employee_name: str
    telegram_id: int
    time_start: str  # "HH:MM"
    time_end: str    # "HH:MM" или ""
    duration_min: int


@dataclass
class Operation:
    date_str: str
    employee_name: str
    telegram_id: int
    operation_type: str
    article: str
    quantity: Optional[int]
    time_start: datetime
    time_end: datetime
    duration_min: int
    extra: str  # доп. тип/комментарий
