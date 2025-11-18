from datetime import datetime, date, time
from zoneinfo import ZoneInfo
from typing import Tuple


def get_now_local(tz_name: str) -> datetime:
    return datetime.now(ZoneInfo(tz_name))


def format_date_dmy(d: date) -> str:
    return d.strftime("%d.%m.%Y")


def parse_time_hm(value: str) -> time:
    return datetime.strptime(value, "%H:%M").time()


def format_time_hm(dt: datetime) -> str:
    return dt.strftime("%H:%M")


def minutes_to_hours_minutes(total_minutes: int) -> Tuple[int, int]:
    hours = total_minutes // 60
    minutes = total_minutes % 60
    return hours, minutes


def format_minutes_human(total_minutes: int) -> str:
    hours, minutes = minutes_to_hours_minutes(total_minutes)
    if hours and minutes:
        return f"{hours} ч {minutes:02d} мин"
    elif hours:
        return f"{hours} ч"
    else:
        return f"{minutes} мин"
