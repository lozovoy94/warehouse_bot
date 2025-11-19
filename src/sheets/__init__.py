# src/sheets/__init__.py

from .client import (
    ensure_sheets_structure,
    get_sheets_client,
    SheetsClient,
)

# Обёртка для обратной совместимости со старым main.py
# main.py вызывает init_sheets_client(config), поэтому просто
# прокидываем вызов в ensure_sheets_structure(config).
def init_sheets_client(app_config):
    """
    Инициализирует глобальный клиент Google Sheets и проверяет структуру
    таблиц. Оставлено для совместимости со старым кодом.
    """
    ensure_sheets_structure(app_config)


__all__ = [
    "SheetsClient",
    "ensure_sheets_structure",
    "get_sheets_client",
    "init_sheets_client",
]
