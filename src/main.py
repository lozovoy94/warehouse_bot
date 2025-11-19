# src/main.py
from __future__ import annotations

import asyncio
import logging
import os

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

from src.bot.handlers import register_handlers
from src.config import load_config
from src.sheets import init_sheets_client, get_sheets_client

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def build_webhook_url(config) -> str:
    """
    Собираем URL вебхука:
    - если есть RAILWAY_PUBLIC_DOMAIN — используем его;
    - иначе берём RAILWAY_PUBLIC_DOMAIN из системных переменных Railway (если есть).
    """
    public_domain = (
        getattr(config, "railway_public_domain", None)
        or os.getenv("RAILWAY_PUBLIC_DOMAIN")
    )
    if not public_domain:
        raise RuntimeError(
            "RAILWAY_PUBLIC_DOMAIN не задан. "
            "Добавь его в Variables или выключи режим webhooks."
        )

    # path хардкодим, чтобы совпадал с тем, что используется в handlers/в Railway
    return f"https://{public_domain}/tg/webhook/{config.webhook_secret}"


def create_web_app(config) -> web.Application:
    bot = Bot(token=config.telegram_bot_token, parse_mode="HTML")
    dp = Dispatcher()

    # Инициализируем Google Sheets
    init_sheets_client(config)

    # Регистрируем хэндлеры и передаём им клиента (они могут также вызвать get_sheets_client()
    register_handlers(dp)

    app = web.Application()

    webhook_path = f"/tg/webhook/{config.webhook_secret}"
    SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
    ).register(app, path=webhook_path)

    setup_application(app, dp, bot=bot)

    return app


async def on_startup(app: web.Application):
    config = app["config"]
    bot: Bot = app["bot"]

    webhook_url = build_webhook_url(config)
    logger.info("Setting webhook: %s", webhook_url)
    await bot.set_webhook(webhook_url, secret_token=config.webhook_secret)


def main():
    config = load_config()

    app = create_web_app(config)
    app["config"] = config

    # В on_startup можно поставить webhook, если нужно
    # (если это не делается где-то ещё)
    # app.on_startup.append(on_startup)

    web.run_app(app, host="0.0.0.0", port=8080)


if __name__ == "__main__":
    main()
