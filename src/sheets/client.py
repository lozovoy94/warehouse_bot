from __future__ import annotations

import datetime as dt
import json
import logging
from dataclasses import dataclass

import gspread
from google.oauth2.service_account import Credentials

from src.config import AppConfig

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


@dataclass
class SheetsClient:
    gc: gspread.Client
    spreadsheet: gspread.Spreadsheet
    tz: dt.tzinfo

    # ---------- construction / infrastructure ----------

    @classmethod
    def from_app_config(cls, config: AppConfig) -> "SheetsClient":
        info = json.loads(config.google_service_account_json)
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)
        gc = gspread.authorize(creds)
        spreadsheet = gc.open_by_key(config.google_sheet_id)

        # timezone
        try:
            import zoneinfo  # py3.9+
            tz = zoneinfo.ZoneInfo(config.timezone)
        except Exception:  # pragma: no cover
            from pytz import timezone

            tz = timezone(config.timezone)

        return cls(gc=gc, spreadsheet=spreadsheet, tz=tz)

    # ---------- low-level helpers ----------

    def _get_ws(self, title: str, header: list[str]) -> gspread.Worksheet:
        try:
            ws = self.spreadsheet.worksheet(title)
        except gspread.WorksheetNotFound:
            ws = self.spreadsheet.add_worksheet(title=title, rows=1000, cols=len(header))
            ws.append_row(header)
            logger.info("Created worksheet %s with header %s", title, header)
        else:
            first_row = ws.row_values(1)
            if not first_row:
                ws.append_row(header)
            # если количество колонок меньше — расширяем
            if len(first_row) < len(header):
                for idx, name in enumerate(header, start=1):
                    if idx > len(first_row):
                        ws.update_cell(1, idx, name)
        return ws

    def ensure_structure(self) -> None:
        """Создаём листы и шапки, если их ещё нет."""
        self._get_ws(
            "Shifts",
            [
                "shift_id",
                "date",
                "user_id",
                "full_name",
                "username",
                "start_at",
                "end_at",
                "duration_minutes",
            ],
        )
        self._get_ws(
            "Operations",
            [
                "timestamp",
                "date",
                "user_id",
                "full_name",
                "username",
                "operation_type",
                "sku",
                "qty",
                "minutes_spent",
                "comment",
                "shift_id",
            ],
        )

    # ---------- domain helpers ----------

    def _now(self) -> dt.datetime:
        return dt.datetime.now(self.tz)

    # -------- shifts --------

    def start_shift(self, user_id: int, full_name: str, username: str | None) -> tuple[bool, str]:
        """
        Возвращает (ok, message_for_user)
        """
        ws = self._get_ws(
            "Shifts",
            [
                "shift_id",
                "date",
                "user_id",
                "full_name",
                "username",
                "start_at",
                "end_at",
                "duration_minutes",
            ],
        )

        now = self._now()
        date_str = now.date().isoformat()

        # Проверяем, нет ли уже незакрытой смены
        rows = ws.get_all_records()
        for row in reversed(rows):
            if int(row["user_id"]) == user_id and not row["end_at"]:
                return False, "У тебя уже есть незакрытая смена. Сначала заверши её."

        shift_id = len(rows) + 1  # простой инкремент по номеру строки
        ws.append_row(
            [
                shift_id,
                date_str,
                user_id,
                full_name,
                username or "",
                now.isoformat(),
                "",
                "",
            ]
        )
        return True, "Смена запущена ✅\nЯ зафиксировал время начала."

    def end_shift(self, user_id: int) -> tuple[bool, str]:
        ws = self._get_ws(
            "Shifts",
            [
                "shift_id",
                "date",
                "user_id",
                "full_name",
                "username",
                "start_at",
                "end_at",
                "duration_minutes",
            ],
        )
        rows = ws.get_all_records()
        if not rows:
            return False, "Активной смены не найдено."

        # Ищем последнюю незакрытую
        row_index = None
        last_row = None
        for idx in range(len(rows) - 1, -1, -1):
            r = rows[idx]
            if int(r["user_id"]) == user_id and not r["end_at"]:
                row_index = idx + 2  # +1 за заголовок, +1 за 0-based
                last_row = r
                break

        if row_index is None or last_row is None:
            return False, "Не нашёл незакрытую смену. Возможно, ты её ещё не запускал."

        now = self._now()
        start_at = dt.datetime.fromisoformat(last_row["start_at"])
        duration_minutes = int((now - start_at).total_seconds() // 60)
        ws.update(
            f"F{row_index}:H{row_index}",
            [[last_row["start_at"], now.isoformat(), duration_minutes]],
        )

        return True, f"Смена завершена ✅\nПродолжительность: ~{duration_minutes} мин."

    def _get_active_shift_id(self, user_id: int) -> int | None:
        ws = self.spreadsheet.worksheet("Shifts")
        rows = ws.get_all_records()
        for r in reversed(rows):
            if int(r["user_id"]) == user_id and not r["end_at"]:
                return int(r["shift_id"])
        return None

    # -------- operations --------

    def add_operation(
        self,
        user_id: int,
        full_name: str,
        username: str | None,
        operation_type: str,
        sku: str | None,
        qty: int | None,
        minutes_spent: int | None,
        comment: str | None,
    ) -> tuple[bool, str]:
        ws = self._get_ws(
            "Operations",
            [
                "timestamp",
                "date",
                "user_id",
                "full_name",
                "username",
                "operation_type",
                "sku",
                "qty",
                "minutes_spent",
                "comment",
                "shift_id",
            ],
        )
        now = self._now()
        shift_id = self._get_active_shift_id(user_id)

        ws.append_row(
            [
                now.isoformat(),
                now.date().isoformat(),
                user_id,
                full_name,
                username or "",
                operation_type,
                sku or "",
                qty or "",
                minutes_spent or "",
                comment or "",
                shift_id or "",
            ]
        )
        if shift_id is None:
            return (
                True,
                "Операция сохранена, но активной смены не найдено.\n"
                "На будущее — лучше сначала запустить смену 😉",
            )
        return True, "Операция сохранена ✅"

    # -------- summary --------

    def get_today_summary(self, user_id: int) -> str:
        today = self._now().date().isoformat()

        shifts_ws = self.spreadsheet.worksheet("Shifts")
        ops_ws = self.spreadsheet.worksheet("Operations")

        shifts = [
            r
            for r in shifts_ws.get_all_records()
            if int(r["user_id"]) == user_id and r["date"] == today
        ]
        ops = [
            r
            for r in ops_ws.get_all_records()
            if int(r["user_id"]) == user_id and r["date"] == today
        ]

        total_shift_minutes = sum(int(r["duration_minutes"] or 0) for r in shifts)
        total_ops = len(ops)
        total_qty = sum(int(r["qty"] or 0) for r in ops)

        lines = [f"Итог за сегодня ({today}):"]
        if shifts:
            lines.append(f"• Смен: {len(shifts)}, всего ~{total_shift_minutes} мин.")
        else:
            lines.append("• Смен: не было.")

        lines.append(f"• Операций: {total_ops}")
        lines.append(f"• Суммарное количество единиц товара: {total_qty}")

        # Разбивка по типу операции
        by_type: dict[str, dict[str, int]] = {}
        for r in ops:
            t = r["operation_type"] or "Без типа"
            bucket = by_type.setdefault(t, {"ops": 0, "qty": 0})
            bucket["ops"] += 1
            bucket["qty"] += int(r["qty"] or 0)

        if by_type:
            lines.append("")
            lines.append("По типам операций:")
            for t, data in by_type.items():
                lines.append(
                    f"• {t}: {data['ops']} операций, {data['qty']} ед."
                )

        return "\n".join(lines)
