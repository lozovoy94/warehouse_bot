# src/sheets/__init__.py
from __future__ import annotations

import logging
from typing import Optional, Any

from .client import SheetsClient, ensure_sheets_structure

logger = logging.getLogger(__name__)

# Глобальный singleton клиента, чтобы им можно было пользоваться из хэндлеров
_sheets_client: Optional[SheetsClient] = None


def init_sheets_client(app_config: Any) -> Optional[SheetsClient]:
    """
    Инициализация Google Sheets.

    Важно:
    - не падаем, если что-то пошло не так;
    - логируем понятную ошибку;
    - возвращаем SheetsClient или None.
    """
    global _sheets_client

    if _sheets_client is not None:
        return _sheets_client

    try:
        # ensure_sheets_structure сам поднимет SheetsClient (через env)
        # и создаст недостающие листы.
        _sheets_client = ensure_sheets_structure(app_config)
        logger.info("Google Sheets client initialized successfully")
    except Exception:
        logger.exception(
            "Failed to initialize Google Sheets client. "
            "Проверь GOOGLE_SERVICE_ACCOUNT_JSON, GOOGLE_SHEET_ID и доступы сервисного аккаунта."
        )
        _sheets_client = None

    return _sheets_client


def get_sheets_client() -> Optional[SheetsClient]:
    """
    Возвращает уже инициализированный SheetsClient (или None).
    Нужен для хэндлеров.
    """
    return _sheets_client
