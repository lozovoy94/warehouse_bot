# src/sheets/__init__.py

from __future__ import annotations

from typing import Optional, Any

from .client import (
    SheetsClient,
    init_sheets_client as _inner_init_sheets_client,
)

# Глобальный клиент, к которому будут обращаться хендлеры
sheets_client: Optional[SheetsClient] = None

__all__ = [
    "SheetsClient",
    "sheets_client",
    "init_sheets_client",
    "get_sheets_client",
]


def init_sheets_client(config: Any) -> SheetsClient:
    """
    Инициализация глобального SheetsClient на основании конфига.
    Вызывается один раз при старте приложения (в main.py).
    """
    global sheets_client
    client = _inner_init_sheets_client(config)
    sheets_client = client
    return client


def get_sheets_client() -> SheetsClient:
    """
    Безопасно вернуть инициализированный SheetsClient.
    Если по какой-то причине он ещё не инициализирован — кидаем RuntimeError,
    чтобы это было видно в логах.
    """
    global sheets_client
    if sheets_client is None:
        raise RuntimeError("Sheets client accessed before initialization")
    return sheets_client
