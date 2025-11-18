import logging
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, date

import gspread
from google.oauth2.service_account import Credentials

from utils.datetime_utils import format_date_dmy, parse_time_hm, format_time_hm
from models.entities import Employee, Shift

logger = logging.getLogger(__name__)

EMPLOYEES_SHEET_TITLE = "Сотрудники"
SHIFTS_SHEET_TITLE = "Смены"
OPERATIONS_SHEET_TITLE = "Операции"

sheets_client: "SheetsClient | None" = None  # глобальный экземпляр


class SheetsClient:
    def __init__(self, sheet_id: str, service_account_info: Dict[str, Any], timezone: str) -> None:
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = Credentials.from_service_account_info(service_account_info, scopes=scopes)
        self._gc = gspread.authorize(creds)
        self._sh = self._gc.open_by_key(sheet_id)
        self._tz = timezone

    # ------------- Инициализация структуры ----------

    def ensure_structure(self) -> None:
        """Создать нужные листы и заголовки, если их нет."""
        logger.info("Ensuring Google Sheets structure...")
        self._ensure_employees_sheet()
        self._ensure_shifts_sheet()
        self._ensure_operations_sheet()
        logger.info("Google Sheets structure OK")

    def _get_or_create_worksheet(self, title: str) -> gspread.Worksheet:
        try:
            ws = self._sh.worksheet(title)
        except gspread.WorksheetNotFound:
            ws = self._sh.add_worksheet(title=title, rows=1000, cols=20)
        return ws

    def _ensure_employees_sheet(self) -> None:
        ws = self._get_or_create_worksheet(EMPLOYEES_SHEET_TITLE)
        headers = ["ID", "Telegram_ID", "Username", "Display_Name", "Дата_регистрации"]
        existing = ws.row_values(1)
        if existing != headers:
            ws.update("A1:E1", [headers])

    def _ensure_shifts_sheet(self) -> None:
        ws = self._get_or_create_worksheet(SHIFTS_SHEET_TITLE)
        headers = [
            "Дата",
            "Сотрудник",
            "Telegram_ID",
            "Время_начала",
            "Время_окончания",
            "Длительность_мин",
            "Комментарий",
        ]
        existing = ws.row_values(1)
        if existing != headers:
            ws.update("A1:G1", [headers])

    def _ensure_operations_sheet(self) -> None:
        ws = self._get_or_create_worksheet(OPERATIONS_SHEET_TITLE)
        headers = [
            "Дата",
            "Сотрудник",
            "Telegram_ID",
            "Тип_операции",
            "Артикул",
            "Количество",
            "Время_начала",
            "Время_окончания",
            "Длительность_мин",
            "Доп_тип_или_коммент",
        ]
        existing = ws.row_values(1)
        if existing != headers:
            ws.update("A1:J1", [headers])

    # ------------- Сотрудники ----------

    def get_employee_by_telegram_id(self, telegram_id: int) -> Optional[Employee]:
        ws = self._sh.worksheet(EMPLOYEES_SHEET_TITLE)
        records = ws.get_all_records()
        for row in records:
            if str(row.get("Telegram_ID")) == str(telegram_id):
                return Employee(
                    internal_id=int(row["ID"]),
                    telegram_id=int(row["Telegram_ID"]),
                    username=row.get("Username") or None,
                    display_name=row.get("Display_Name") or "",
                    registered_at=row.get("Дата_регистрации") or "",
                )
        return None

    def register_employee(self, telegram_id: int, username: Optional[str], display_name: str, today: date) -> Employee:
        ws = self._sh.worksheet(EMPLOYEES_SHEET_TITLE)
        records = ws.get_all_records()
        new_id = len(records) + 1
        date_str = format_date_dmy(today)
        row = [new_id, telegram_id, username or "", display_name, date_str]
        ws.append_row(row, value_input_option="USER_ENTERED")
        return Employee(
            internal_id=new_id,
            telegram_id=telegram_id,
            username=username,
            display_name=display_name,
            registered_at=date_str,
        )

    # ------------- Смены ----------

    def has_open_shift_for_today(self, telegram_id: int, today: date) -> bool:
        return self._find_open_shift_row(telegram_id, today) is not None

    def _find_open_shift_row(self, telegram_id: int, day: date) -> Optional[int]:
        ws = self._sh.worksheet(SHIFTS_SHEET_TITLE)
        all_values = ws.get_all_values()
        if len(all_values) <= 1:
            return None
        date_str = format_date_dmy(day)

        # all_values[0] - заголовки, дальше данные
        for idx, row in enumerate(all_values[1:], start=2):  # индексы строк 2+
            row_date = row[0] if len(row) > 0 else ""
            row_tg = row[2] if len(row) > 2 else ""
            end_time = row[4] if len(row) > 4 else ""
            if row_date == date_str and str(row_tg) == str(telegram_id) and not end_time:
                return idx
        return None

    def start_shift(self, employee: Employee, now_local: datetime) -> None:
        ws = self._sh.worksheet(SHIFTS_SHEET_TITLE)
        date_str = format_date_dmy(now_local.date())
        start_time_str = format_time_hm(now_local)
        row = [
            date_str,
            employee.display_name,
            employee.telegram_id,
            start_time_str,
            "",
            "",
            "",
        ]
        ws.append_row(row, value_input_option="USER_ENTERED")

    def end_shift(self, telegram_id: int, now_local: datetime) -> bool:
        ws = self._sh.worksheet(SHIFTS_SHEET_TITLE)
        row_index = self._find_open_shift_row(telegram_id, now_local.date())
        if row_index is None:
            return False

        # Читаем строку целиком
        row = ws.row_values(row_index)
        start_time_str = row[3] if len(row) > 3 else ""
        if not start_time_str:
            # странный кейс, но считаем, что начали в это же время
            start_time_str = format_time_hm(now_local)

        start_time = datetime.combine(
            now_local.date(),
            parse_time_hm(start_time_str),
            tzinfo=now_local.tzinfo,
        )
        end_time_str = format_time_hm(now_local)
        duration_min = int((now_local - start_time).total_seconds() // 60)
        if duration_min < 0:
            duration_min = 0

        ws.update(
            f"E{row_index}:F{row_index}",
            [[end_time_str, duration_min]],
        )
        return True

    def get_shifts_for_employee_and_date(self, telegram_id: int, day: date) -> List[Shift]:
        ws = self._sh.worksheet(SHIFTS_SHEET_TITLE)
        records = ws.get_all_records()
        date_str = format_date_dmy(day)
        shifts: List[Shift] = []

        for row in records:
            if row.get("Дата") != date_str:
                continue
            if str(row.get("Telegram_ID")) != str(telegram_id):
                continue
            start = row.get("Время_начала") or ""
            end = row.get("Время_окончания") or ""
            dur = row.get("Длительность_мин") or 0
            try:
                dur_int = int(dur)
            except Exception:
                dur_int = 0
            shifts.append(
                Shift(
                    date_str=date_str,
                    employee_name=row.get("Сотрудник") or "",
                    telegram_id=int(row.get("Telegram_ID")),
                    time_start=start,
                    time_end=end,
                    duration_min=dur_int,
                )
            )

        return shifts

    # ------------- Операции ----------

    def append_operation(
        self,
        employee: Employee,
        op_type: str,
        date_str: str,
        article: str,
        quantity: Optional[int],
        time_start: datetime,
        time_end: datetime,
        extra: str,
    ) -> None:
        ws = self._sh.worksheet(OPERATIONS_SHEET_TITLE)
        start_str = time_start.strftime("%H:%M")
        end_str = time_end.strftime("%H:%M")
        duration_min = int((time_end - time_start).total_seconds() // 60)
        if duration_min < 0:
            duration_min = 0
        row = [
            date_str,
            employee.display_name,
            employee.telegram_id,
            op_type,
            article,
            quantity if quantity is not None else "",
            start_str,
            end_str,
            duration_min,
            extra,
        ]
        ws.append_row(row, value_input_option="USER_ENTERED")

    def get_operations_for_employee_and_date(
        self, telegram_id: int, day: date
    ) -> List[Dict[str, Any]]:
        ws = self._sh.worksheet(OPERATIONS_SHEET_TITLE)
        records = ws.get_all_records()
        date_str = format_date_dmy(day)
        result: List[Dict[str, Any]] = []
        for row in records:
            if row.get("Дата") != date_str:
                continue
            if str(row.get("Telegram_ID")) != str(telegram_id):
                continue
            result.append(row)
        return result

    # ------------- Отчёт за день для сотрудника ----------

    def build_employee_daily_summary(
        self, telegram_id: int, day: date, now_local: datetime
    ) -> Dict[str, Any]:
        date_str = format_date_dmy(day)
        shifts = self.get_shifts_for_employee_and_date(telegram_id, day)
        operations = self.get_operations_for_employee_and_date(telegram_id, day)

        # Смены: если есть открытая на сегодня без конца - считаем до now_local
        total_shift_minutes = 0
        shift_ranges: List[str] = []

        for shift in shifts:
            start = shift.time_start
            end = shift.time_end
            duration = shift.duration_min

            if not end:
                # открытая смена - считаем до now_local (но не пишем обратно в таблицу)
                if start:
                    start_dt = datetime.combine(
                        day,
                        parse_time_hm(start),
                        tzinfo=now_local.tzinfo,
                    )
                    duration = int((now_local - start_dt).total_seconds() // 60)
                    if duration < 0:
                        duration = 0
                    end = "…"
            total_shift_minutes += duration
            range_str = f"{start or '?'}–{end or '?'}"
            shift_ranges.append(range_str)

        # Операции
        fbs_units = 0
        fbs_minutes = 0
        pack_units = 0
        pack_minutes = 0
        other_minutes = 0

        for op in operations:
            op_type = op.get("Тип_операции") or ""
            qty_raw = op.get("Количество")
            qty = 0
            if qty_raw not in (None, ""):
                try:
                    qty = int(qty_raw)
                except Exception:
                    qty = 0
            dur_raw = op.get("Длительность_мин") or 0
            try:
                dur = int(dur_raw)
            except Exception:
                dur = 0

            if op_type == "Сборка FBS":
                fbs_units += qty
                fbs_minutes += dur
            elif op_type == "Упаковка":
                pack_units += qty
                pack_minutes += dur
            elif op_type == "Прочие задачи":
                other_minutes += dur

        total_ops_minutes = fbs_minutes + pack_minutes + other_minutes
        residue_minutes = max(total_shift_minutes - total_ops_minutes, 0)

        return {
            "date_str": date_str,
            "shift_ranges": shift_ranges,
            "total_shift_minutes": total_shift_minutes,
            "fbs_units": fbs_units,
            "fbs_minutes": fbs_minutes,
            "pack_units": pack_units,
            "pack_minutes": pack_minutes,
            "other_minutes": other_minutes,
            "total_ops_minutes": total_ops_minutes,
            "residue_minutes": residue_minutes,
        }

    # ------------- Admin summary по дате ----------

    def build_admin_summary_for_date(self, day: date) -> Dict[str, Any]:
        date_str = format_date_dmy(day)
        shifts_ws = self._sh.worksheet(SHIFTS_SHEET_TITLE)
        ops_ws = self._sh.worksheet(OPERATIONS_SHEET_TITLE)

        shift_records = shifts_ws.get_all_records()
        op_records = ops_ws.get_all_records()

        # агрегируем по Telegram_ID
        stats: Dict[str, Dict[str, Any]] = {}

        # Смены
        for row in shift_records:
            if row.get("Дата") != date_str:
                continue
            tg_id_str = str(row.get("Telegram_ID"))
            if tg_id_str not in stats:
                stats[tg_id_str] = {
                    "employee_name": row.get("Сотрудник") or "",
                    "telegram_id": tg_id_str,
                    "shift_minutes": 0,
                    "shift_count": 0,
                    "fbs_units": 0,
                    "fbs_minutes": 0,
                    "pack_units": 0,
                    "pack_minutes": 0,
                    "other_minutes": 0,
                }
            dur_raw = row.get("Длительность_мин") or 0
            try:
                dur = int(dur_raw)
            except Exception:
                dur = 0
            stats[tg_id_str]["shift_minutes"] += dur
            stats[tg_id_str]["shift_count"] += 1

        # Операции
        for row in op_records:
            if row.get("Дата") != date_str:
                continue
            tg_id_str = str(row.get("Telegram_ID"))
            if tg_id_str not in stats:
                stats[tg_id_str] = {
                    "employee_name": row.get("Сотрудник") or "",
                    "telegram_id": tg_id_str,
                    "shift_minutes": 0,
                    "shift_count": 0,
                    "fbs_units": 0,
                    "fbs_minutes": 0,
                    "pack_units": 0,
                    "pack_minutes": 0,
                    "other_minutes": 0,
                }

            op_type = row.get("Тип_операции") or ""
            qty_raw = row.get("Количество")
            qty = 0
            if qty_raw not in (None, ""):
                try:
                    qty = int(qty_raw)
                except Exception:
                    qty = 0
            dur_raw = row.get("Длительность_мин") or 0
            try:
                dur = int(dur_raw)
            except Exception:
                dur = 0

            if op_type == "Сборка FBS":
                stats[tg_id_str]["fbs_units"] += qty
                stats[tg_id_str]["fbs_minutes"] += dur
            elif op_type == "Упаковка":
                stats[tg_id_str]["pack_units"] += qty
                stats[tg_id_str]["pack_minutes"] += dur
            elif op_type == "Прочие задачи":
                stats[tg_id_str]["other_minutes"] += dur

        return {
            "date_str": date_str,
            "employees": list(stats.values()),
        }


def init_sheets_client(config) -> SheetsClient:
    global sheets_client
    sheets_client = SheetsClient(
        sheet_id=config.google_sheet_id,
        service_account_info=config.google_service_account_info,
        timezone=config.timezone,
    )
    return sheets_client
