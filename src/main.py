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
    public_domain = (
        getattr(config, "railway_public_domain", None)
        or os.getenv("RAILWAY_PUBLIC_DOMAIN")
    )
    if not public_domain:
        raise RuntimeError(
            "RAILWAY_PUBLIC_DOMAIN не задан. "
            "Добавь его в Variables или выключи режим webhooks."
        )

    return f"https://{public_domain}/tg/webhook/{config.webhook_secret}"


async def on_startup(app: web.Application):
    """
    Колбэк старта aiohttp-приложения: ставим вебхук в Telegram.
    """
    bot: Bot = app["bot"]
    config = app["config"]

    webhook_url = build_webhook_url(config)
    await bot.set_webhook(
        url=webhook_url,
        allowed_updates=app["dispatcher"].resolve_used_update_types(),
    )
    logger.info("Webhook set to %s", webhook_url)


def create_web_app(config) -> web.Application:
    # aiogram 3.7+: parse_mode задаём через DefaultBotProperties
    bot = Bot(
        token=config.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    # Инициализация Google Sheets
    init_sheets_client(config)

    # Регистрируем хендлеры, передаём конфиг
    register_handlers(dp, config)

    app = web.Application()

    webhook_path = f"/tg/webhook/{config.webhook_secret}"
    SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
    ).register(app, path=webhook_path)

    setup_application(app, dp, bot=bot)

    app["bot"] = bot
    app["config"] = config
    app["dispatcher"] = dp

    # При старте приложения — ставим вебхук
    app.on_startup.append(on_startup)

    return app


def main():
    config = load_config()
    app = create_web_app(config)
    web.run_app(app, host="0.0.0.0", port=8080)


if __name__ == "__main__":
    main()
