from __future__ import annotations

import asyncio
import logging
import sys

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.webhook.aiohttp_server import (
    SimpleRequestHandler,
    setup_application,
)

from src.config import AppConfig
from src.sheets import init_sheets_client
from src.bot.handlers import register_handlers

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s:%(name)s:%(message)s",
)
logger = logging.getLogger(__name__)


def create_web_app(config: AppConfig) -> web.Application:
    # инициализируем Google Sheets один раз при старте
    init_sheets_client(config)

    bot = Bot(
        token=config.telegram_bot_token,
        default=DefaultBotProperties(parse_mode="HTML"),
    )
    dp = Dispatcher()

    register_handlers(dp, config)

    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path="/tg/webhook")
    setup_application(app, dp, bot=bot)

    # на старте выставляем вебхук
    async def on_startup(app_: web.Application):
        if config.railway_public_domain:
            webhook_url = f"https://{config.railway_public_domain}/tg/webhook"
            await bot.set_webhook(webhook_url)
            logger.info("Webhook set to %s", webhook_url)
        else:
            logger.info("RAILWAY_PUBLIC_DOMAIN is not set, webhook will not be configured")

    app.on_startup.append(on_startup)

    return app


def main() -> None:
    config = AppConfig.from_env()
    app = create_web_app(config)
    web.run_app(app, host="0.0.0.0", port=8080)


if __name__ == "__main__":
    try:
        main()
    except Exception:  # pragma: no cover
        logging.exception("Fatal error in main")
        sys.exit(1)
