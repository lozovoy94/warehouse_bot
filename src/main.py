# src/main.py
from __future__ import annotations

import logging
import os

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

from src.bot.handlers import register_handlers
from src.config import load_config
from src.sheets import init_sheets_client

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def build_webhook_url(config) -> str:
    """
    Собираем URL вебхука:
    - если есть railway_public_domain в конфиге — используем его;
    - иначе берём RAILWAY_PUBLIC_DOMAIN из env.
    """
    public
