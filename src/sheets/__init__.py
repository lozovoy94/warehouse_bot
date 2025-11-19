from __future__ import annotations

import logging
from typing import Optional

from .client import SheetsClient
from src.config import AppConfig

logger = logging.getLogger(__name__)

_sheets_client: Optional[SheetsClient] = None


def init_sheets_client(config: AppConfig) -> SheetsClient:
    global _sheets_client
    logger.info("Ensuring Google Sheets structure...")
    client = SheetsClient.from_app_config(config)
    client.ensure_structure()
    _sheets_client = client
    logger.info("Google Sheets client initialized successfully")
    return client


def get_sheets_client() -> SheetsClient | None:
    return _sheets_client
