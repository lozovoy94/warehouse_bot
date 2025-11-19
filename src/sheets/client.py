# src/sheets/client.py

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, date, time, timedelta
from typing import Optional, List

import gspread
from google.oauth2 import service_account

try:
    import zoneinfo  # Python 3.13
except ImportError:  # на всякий случай
    from backports import zoneinfo  # type: ignore

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# Глобальный singleton, чтобы к нему обращаться из хендлеров
_sheets_client: Optional["SheetsClient"] = None


@dataclass
class SheetsConfig:
    service_account_json: str
    spreadsheet_id: str
    timezone: str = "Europe/Moscow"


def _detect_config_from_app_config(app_config) -> SheetsConfig:
    """
    Пытаемся аккуратно вытащить настройки из объекта config,
    а если чего-то не хватает — добираем из окружения.
    """

    # service account JSON
    sa_json = None
    for attr in (
        "google_service_account_json",
        "service_account_json",
        "warehouse_service_account_json",
        "gcp_service_account_json",
    ):
        if hasattr(app_config, attr):
            sa_json = getattr(app_config, attr)
            if sa_json:
                break

    if not sa_json:
        sa_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")

    # spreadsheet id
    spreadsheet_id = None
    for attr in (
        "google_spreadsheet_id",
        "spreadsheet_id",
        "warehouse_spreadsheet_id",
        "sheet_id",
    ):
        if hasattr(app_config, attr):
            spreadsheet_id = getattr(app_config, attr)
            if spreadsheet_id:
                break

    if not spreadsheet_id:
        spreadsheet_id = os.environ.get("GOOGLE_SPREADSHEET_ID", "")

    # timezone
    tz_name = None
    for attr in ("timezone", "tz", "time_zone"):
        if hasattr(app_config, attr):
            tz_name = getattr(app_config, attr)
            if tz_name:
                break

    if not tz_name:
        tz_name = os.environ.get("TZ", "Europe/Moscow")

    return SheetsConfig(
        service_account_json=sa_json,
        spreadsheet_id=spreadsheet_id,
        timezone=tz_name,
    )


class SheetsClient:
    """
    Клиент для работы с Google Sheets.

    Сейчас реализовано:
    - структура с листом Shifts
    - логирование начала/конца смен
    - сводка по сменам за сегодня
    """

    SHIFTS_SHEET_NAME = "Shifts"

    # Порядок колонок в Shifts:
    # A: Date (YYYY-MM-DD)
    # B: User ID
    # C: User Name
    # D: Shift Start (HH:MM:SS)
    # E: Shift End (HH:MM:SS)
    # F: Total Minutes
    # G: Comment (пока не используется)
    SHIFTS_HEADERS: List[str] = [
        "Date",
        "User ID",
        "User Name",
        "Shift Start",
        "Shift End",
        "Total Minutes",
        "Comment",
    ]

    def __init__(self, gc: gspread.Client, spreadsheet: gspread.Spreadsheet, tz_name: str):
        self.gc = gc
        self.spreadsheet = spreadsheet
        self.tz_name = tz_name
        try:
            self.tz = zoneinfo.ZoneInfo(tz_name)
        except Exception:
            self.tz = zoneinfo.ZoneInfo("Europe/Moscow")

    @classmethod
    def from_app_config(cls, app_config) -> "SheetsClient":
        cfg = _detect_config_from_app_config(app_config)

        if not cfg.service_account_json:
            raise RuntimeError("Service account JSON is empty/not configured")
        if not cfg.spreadsheet_id:
            raise RuntimeError("Spreadsheet ID is empty/not configured")

        info = json.loads(cfg.service_account_json)
        credentials = service_account.Credentials.from_service_account_info(
            info,
            scopes=SCOPES,
        )
        gc = gspread.authorize(credentials)
        spreadsheet = gc.open_by_key(cfg.spreadsheet_id)

        return cls(gc=gc, spreadsheet=spreadsheet, tz_name=cfg.timezone)

    # -------------------------------------------------------------------------
    # Структура таблицы
    # -------------------------------------------------------------------------

    def ensure_structure(self) -> None:
        """
        Проверяем, что все нужные листы существуют и имеют заголовки.
        Сейчас нужен только лист Shifts.
        """
        logger.info("Ensuring Google Sheets structure...")

        try:
            ws = self.spreadsheet.worksheet(self.SHIFTS_SHEET_NAME)
        except gspread.WorksheetNotFound:
            ws = self.spreadsheet.add_worksheet(
                title=self.SHIFTS_SHEET_NAME,
                rows=1000,
                cols=len(self.SHIFTS_HEADERS),
            )

        # Заголовки
        existing = ws.row_values(1)
        if existing != self.SHIFTS_HEADERS:
            ws.resize(rows=1)  # не трогаем кол-во колонок, только строк
            ws.update("A1", [self.SHIFTS_HEADERS])

        logger.info("Google Sheets structure OK")

    # -------------------------------------------------------------------------
    # Работа со сменами
    # -------------------------------------------------------------------------

    def _now(self) -> datetime:
        return datetime.now(self.tz)

    def _get_shifts_sheet(self) -> gspread.Worksheet:
        return self.spreadsheet.worksheet(self.SHIFTS_SHEET_NAME)

    def log_shift_start(self, user_id: int, user_name: str) -> None:
        """
        Добавляем строку о начале смены.
        """
        ws = self._get_shifts_sheet()
        now = self._now()

        date_str = now.date().isoformat()
        time_str = now.strftime("%H:%M:%S")

        row = [
            date_str,
            str(user_id),
            user_name,
            time_str,  # Shift Start
            "",        # Shift End
            "",        # Total Minutes
            "",        # Comment
        ]
        ws.append_row(row, value_input_option="USER_ENTERED")

    def log_shift_end(self, user_id: int) -> None:
        """
        Находим последнюю незакрытую смену пользователя и проставляем время конца.
        """
        ws = self._get_shifts_sheet()
        values = ws.get_all_values()

        if len(values) <= 1:
            # только заголовок, закрывать нечего
            return

        # Индексы колонок (0-based)
        COL_USER_ID = 1
        COL_START = 3
        COL_END = 4
        COL_TOTAL_MIN = 5

        now = self._now()
        date_today = now.date()
        end_str = now.strftime("%H:%M:%S")

        # ищем снизу вверх
        target_row_index: Optional[int] = None
        for idx in range(len(values) - 1, 0, -1):
            row = values[idx]
            if len(row) <= COL_USER_ID:
                continue
            if row[COL_USER_ID] != str(user_id):
                continue

            # если уже есть конец смены — пропускаем
            if len(row) > COL_END and row[COL_END]:
                continue

            target_row_index = idx + 1  # gspread 1-based
            start_str = row[COL_START] if len(row) > COL_START else ""
            break

        if target_row_index is None:
            # нет незакрытой смены — просто ничего не делаем
            return

        # считаем длительность, если есть время начала
        total_minutes: Optional[int] = None
        try:
            if start_str:
                start_time = datetime.strptime(start_str, "%H:%M:%S").time()
                start_dt = datetime.combine(date_today, start_time, tzinfo=self.tz)
                delta: timedelta = now - start_dt
                total_minutes = int(delta.total_seconds() // 60)
        except Exception:
            total_minutes = None

        updates = {
            f"E{target_row_index}": end_str,
        }
        if total_minutes is not None:
            updates[f"F{target_row_index}"] = str(total_minutes)

        # пакетное обновление
        data = [
            {"range": cell, "values": [[value]]}
            for cell, value in updates.items()
        ]
        ws.batch_update(data, value_input_option="USER_ENTERED")

    def get_today_summary(self, user_id: int) -> str:
        """
        Возвращает текстовую сводку по всем сменам пользователя за сегодня.
        """
        ws = self._get_shifts_sheet()
        records = ws.get_all_records()  # [{'Date': ..., 'User ID': ..., ...}, ...]

        today_str = self._now().date().isoformat()
        user_str = str(user_id)

        user_rows = [
            r for r in records
            if str(r.get("User ID", "")) == user_str
            and str(r.get("Date", "")) == today_str
        ]

        if not user_rows:
            return "За сегодня смен для тебя пока не зафиксировано."

        total_minutes = 0
        completed_shifts = 0

        lines: List[str] = []

        for r in user_rows:
            start = r.get("Shift Start") or ""
            end = r.get("Shift End") or ""
            minutes_raw = r.get("Total Minutes")

            try:
                minutes = int(minutes_raw) if minutes_raw else 0
            except Exception:
                minutes = 0

            if end:
                completed_shifts += 1
                total_minutes += minutes

            lines.append(f"- {start or '—'} → {end or '—'} ({minutes} мин)")

        hours = total_minutes // 60
        minutes_rem = total_minutes % 60

        summary_header = (
            f"Сегодняшние смены:\n"
            f"Всего смен: {len(user_rows)} (закрытых: {completed_shifts})\n"
            f"Общее время: {hours} ч {minutes_rem} мин\n"
        )

        return summary_header + "\n".join(lines)


# -------------------------------------------------------------------------
# Функции, которые вызываются из main.py / хендлеров
# -------------------------------------------------------------------------


def ensure_sheets_structure(app_config) -> None:
    """
    Создаём глобальный клиент и убеждаемся, что структура таблицы готова.
    Вызывается при старте приложения.
    """
    global _sheets_client
    logger.info("Ensuring Google Sheets structure...")

    if _sheets_client is None:
        _sheets_client = SheetsClient.from_app_config(app_config)

    _sheets_client.ensure_structure()

    logger.info("Google Sheets structure OK")


def get_sheets_client() -> Optional[SheetsClient]:
    """
    Возвращаем уже инициализированный глобальный клиент.
    Может вернуть None, если ensure_sheets_structure ещё не вызывался.
    """
    return _sheets_client
