# src/sheets/client.py
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Optional

import gspread
from google.oauth2.service_account import Credentials

logger = logging.getLogger(__name__)

# Столбцы и названия листов — оставил максимально нейтральными.
# Если у тебя уже были листы с такими именами/структурой — они подхватятся как есть.
SHEET_SHIFTS = "Смены"
SHEET_TASKS = "Операции"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


@dataclass
class SheetsConfig:
    """Мини-конфиг только для Google Sheets."""

    spreadsheet_id: str
    service_account_json: str
    timezone: str = "Europe/Moscow"


class SheetsClient:
    """
    Обёртка над gspread.

    Содержит только то, что реально нужно боту:
    - проверка/создание структуры;
    - старт/завершение смены;
    - добавление операций;
    - получение краткой сводки за день (если нужно).
    """

    def __init__(self, gc: gspread.Client, cfg: SheetsConfig):
        self._gc = gc
        self._cfg = cfg
        self._spreadsheet = self._gc.open_by_key(cfg.spreadsheet_id)

    # ------------------------------------------------------------------ #
    #   Утилиты и инициализация
    # ------------------------------------------------------------------ #

    @classmethod
    def from_app_config(cls, app_config: Any) -> "SheetsClient":
        """
        Универсальный конструктор, который:
        1. В первую очередь берёт данные ИЗ ПЕРЕМЕННЫХ ОКРУЖЕНИЯ:
           - GOOGLE_SHEET_ID
           - GOOGLE_SERVICE_ACCOUNT_JSON
        2. Если там пусто — пробует вытащить из app_config (на всякий случай).
        """

        # 1. Пробуем из env (основной способ)
        sheet_id = os.getenv("GOOGLE_SHEET_ID", "").strip()
        sa_json_raw = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
        timezone = os.getenv("TZ") or os.getenv("TIMEZONE") or "Europe/Moscow"

        # 2. Если вдруг env пустые — пробуем из app_config
        if not sheet_id and app_config is not None:
            # разные возможные варианты имён атрибутов
            for name in (
                "google_sheet_id",
                "spreadsheet_id",
                "sheet_id",
            ):
                if hasattr(app_config, name):
                    val = getattr(app_config, name)
                    if val:
                        sheet_id = str(val).strip()
                        break
                # nested: app_config.sheets.google_sheet_id и т.п.
                for prefix in ("google", "sheets"):
                    nested = getattr(app_config, prefix, None)
                    if nested is not None and hasattr(nested, name):
                        val = getattr(nested, name)
                        if val:
                            sheet_id = str(val).strip()
                            break

        if not sa_json_raw and app_config is not None:
            for name in (
                "google_service_account_json",
                "service_account_json",
            ):
                if hasattr(app_config, name):
                    val = getattr(app_config, name)
                    if val:
                        sa_json_raw = str(val).strip()
                        break
                for prefix in ("google", "sheets"):
                    nested = getattr(app_config, prefix, None)
                    if nested is not None and hasattr(nested, name):
                        val = getattr(nested, name)
                        if val:
                            sa_json_raw = str(val).strip()
                            break

        if not sheet_id:
            raise RuntimeError("Spreadsheet ID is empty/not configured")

        if not sa_json_raw:
            raise RuntimeError("Service account JSON is empty/not configured")

        try:
            sa_info = json.loads(sa_json_raw)
        except json.JSONDecodeError as e:
            raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON is not valid JSON") from e

        creds = Credentials.from_service_account_info(sa_info, scopes=SCOPES)
        gc = gspread.authorize(creds)

        cfg = SheetsConfig(
            spreadsheet_id=sheet_id,
            service_account_json=sa_json_raw,
            timezone=timezone,
        )

        return cls(gc, cfg)

    # ------------------------------------------------------------------ #
    #   Структура таблиц
    # ------------------------------------------------------------------ #

    def _get_or_create_worksheet(self, title: str, rows: int = 1000, cols: int = 20):
        try:
            return self._spreadsheet.worksheet(title)
        except gspread.WorksheetNotFound:
            logger.info("Creating worksheet %s", title)
            return self._spreadsheet.add_worksheet(title=title, rows=rows, cols=cols)

    def ensure_structure(self) -> None:
        """
        Проверяем, что есть листы и заголовки. Если нет — создаём.
        Это безопасно вызывать много раз.
        """
        # Смены
        ws_shifts = self._get_or_create_worksheet(SHEET_SHIFTS)
        header_shifts = [
            "shift_id",
            "tg_user_id",
            "tg_username",
            "full_name",
            "date",
            "start_dt",
            "end_dt",
            "duration_min",
        ]
        if ws_shifts.row_values(1) != header_shifts:
            ws_shifts.clear()
            ws_shifts.insert_row(header_shifts, 1)

        # Операции
        ws_tasks = self._get_or_create_worksheet(SHEET_TASKS)
        header_tasks = [
            "timestamp",
            "shift_id",
            "tg_user_id",
            "task_type",
            "sku",
            "quantity",
            "minutes_spent",
            "comment",
        ]
        if ws_tasks.row_values(1) != header_tasks:
            ws_tasks.clear()
            ws_tasks.insert_row(header_tasks, 1)

    # ------------------------------------------------------------------ #
    #   Логика смен и операций
    # ------------------------------------------------------------------ #

    def _new_shift_id(self) -> str:
        ws = self._spreadsheet.worksheet(SHEET_SHIFTS)
        rows = ws.col_values(1)  # shift_id
        if len(rows) <= 1:
            return "1"
        try:
            last = int(rows[-1])
        except ValueError:
            last = len(rows) - 1
        return str(last + 1)

    def _get_open_shift_row(self, tg_user_id: int) -> Optional[int]:
        """
        Возвращает номер строки открытой смены пользователя (без end_dt), либо None.
        """
        ws = self._spreadsheet.worksheet(SHEET_SHIFTS)
        user_ids = ws.col_values(2)[1:]  # tg_user_id, пропускаем заголовок
        end_vals = ws.col_values(7)[1:]  # end_dt

        for idx, (uid, end_dt) in enumerate(zip(user_ids, end_vals), start=2):
            if str(uid) == str(tg_user_id) and not end_dt:
                return idx
        return None

    def start_shift(
        self,
        tg_user_id: int,
        tg_username: str,
        full_name: str,
        now: datetime,
    ) -> str:
        """
        Старт смены. Если смена уже открыта — просто возвращаем её id.
        """
        ws = self._spreadsheet.worksheet(SHEET_SHIFTS)
        open_row = self._get_open_shift_row(tg_user_id)
        if open_row is not None:
            # уже есть открытая смена
            shift_id = ws.cell(open_row, 1).value
            return shift_id

        shift_id = self._new_shift_id()
        date_str = now.date().isoformat()
        dt_str = now.isoformat()

        row = [
            shift_id,
            str(tg_user_id),
            tg_username or "",
            full_name or "",
            date_str,
            dt_str,
            "",  # end_dt
            "",  # duration_min
        ]
        ws.append_row(row)
        return shift_id

    def finish_shift(self, tg_user_id: int, now: datetime) -> Optional[str]:
        """
        Завершение смены. Возвращает shift_id или None, если открытой нет.
        """
        ws = self._spreadsheet.worksheet(SHEET_SHIFTS)
        row_idx = self._get_open_shift_row(tg_user_id)
        if row_idx is None:
            return None

        start_dt_str = ws.cell(row_idx, 6).value  # start_dt
        duration_min = ""
        if start_dt_str:
            try:
                start_dt = datetime.fromisoformat(start_dt_str)
                duration_min = str(int((now - start_dt).total_seconds() // 60))
            except Exception:
                logger.warning("Failed to parse start_dt: %s", start_dt_str)

        ws.update_cell(row_idx, 7, now.isoformat())
        if duration_min:
            ws.update_cell(row_idx, 8, duration_min)

        shift_id = ws.cell(row_idx, 1).value
        return shift_id

    def add_task(
        self,
        tg_user_id: int,
        task_type: str,
        sku: str,
        quantity: int,
        minutes_spent: int,
        comment: str,
        now: datetime,
    ) -> Optional[str]:
        """
        Добавить операцию в текущую смену.
        Возвращает shift_id или None, если смены нет.
        """
        ws_shifts = self._spreadsheet.worksheet(SHEET_SHIFTS)
        ws_tasks = self._spreadsheet.worksheet(SHEET_TASKS)

        row_idx = self._get_open_shift_row(tg_user_id)
        if row_idx is None:
            return None

        shift_id = ws_shifts.cell(row_idx, 1).value
        ts_str = now.isoformat()

        row = [
            ts_str,
            shift_id,
            str(tg_user_id),
            task_type,
            sku,
            int(quantity) if quantity is not None else "",
            int(minutes_spent) if minutes_spent is not None else "",
            comment or "",
        ]
        ws_tasks.append_row(row)
        return shift_id

    # при необходимости сюда можно добавить методы для "краткого итога за день" и т.п.


# ---------------------------------------------------------------------- #
#   Функция верхнего уровня, которую вызывает main через init_sheets_client
# ---------------------------------------------------------------------- #


def ensure_sheets_structure(app_config: Any) -> SheetsClient:
    """
    Создаёт SheetsClient (через env/app_config) и гарантирует наличие структуры.
    Возвращает готовый клиент.
    """
    client = SheetsClient.from_app_config(app_config)
    client.ensure_structure()
    logger.info("Google Sheets structure OK")
    return client
