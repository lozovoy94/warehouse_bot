from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from .client import SheetsClient

if TYPE_CHECKING:
    # Только для type hints, чтобы не ловить циклические импорты
    from ..config import Config

# Глобальный экземпляр SheetsClient, на который ссылаются хэндлеры
sheets_client: Optional[SheetsClient] = None


def init_sheets_client(config: "Config") -> SheetsClient:
    """
    Инициализирует глобальный клиент Google Sheets и возвращает его.
    Вызывается один раз из main.py при старте приложения.
    """
    global sheets_client

    if sheets_client is None:
        sheets_client = SheetsClient(
            sheet_id=config.google_sheet_id,
            service_account_info=config.google_service_account_info,
            timezone=config.timezone,
        )

    return sheets_client


__all__ = [
    "SheetsClient",
    "sheets_client",
    "init_sheets_client",
]
