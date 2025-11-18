import asyncio
import logging

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Update

from .config import load_config, Config
from .logging_config import setup_logging
from .sheets import init_sheets_client
from .bot import register_handlers


logger = logging.getLogger(__name__)


async def run_polling(config: Config) -> None:
    """Локальный режим: polling."""
    bot = Bot(
        token=config.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    register_handlers(dp, config)

    logger.info("Starting bot in polling mode...")
    await dp.start_polling(bot)


def create_web_app(config: Config) -> web.Application:
    """Production режим: webhook + aiohttp."""
    app = web.Application()
    app["config"] = config

    bot = Bot(
        token=config.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    register_handlers(dp, config)

    app["bot"] = bot
    app["dp"] = dp

    webhook_path = f"/tg/webhook/{config.webhook_secret}"
    if not config.railway_public_domain:
        raise RuntimeError("RAILWAY_PUBLIC_DOMAIN must be set in production environment")
    webhook_url = config.railway_public_domain.rstrip("/") + webhook_path

    async def handle_webhook(request: web.Request) -> web.Response:
        token = request.match_info.get("token")
        if token != config.webhook_secret:
            return web.Response(status=403, text="Forbidden")

        data = await request.text()
        try:
            update = Update.model_validate_json(data)
        except Exception:
            logger.exception("Failed to parse update JSON")
            return web.Response(status=400, text="Bad Request")

        await dp.feed_update(bot, update)
        return web.Response(status=200)

    app.router.add_post("/tg/webhook/{token}", handle_webhook)

    async def on_startup(app_: web.Application) -> None:
        logger.info("Setting webhook: %s", webhook_url)
        # Telegram требует https — убедись, что RAILWAY_PUBLIC_DOMAIN с https-схемой
        await bot.set_webhook(webhook_url, drop_pending_updates=True)

    async def on_shutdown(app_: web.Application) -> None:
        logger.info("Deleting webhook...")
        try:
            await bot.delete_webhook(drop_pending_updates=False)
        except Exception:
            logger.exception("Error deleting webhook")
        await bot.session.close()
        logger.info("Webhook deleted and bot session closed.")

    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)

    return app


def main() -> None:
    setup_logging()
    config = load_config()

    # --- Инициализация Google Sheets клиента ---
    try:
        sc = init_sheets_client(config)
    except Exception:
        logger.exception(
            "Failed to initialize Google Sheets client. "
            "Проверь GOOGLE_SERVICE_ACCOUNT_JSON, GOOGLE_SHEET_ID и доступы сервисного аккаунта."
        )
        raise

    if sc is None:
        logger.error("init_sheets_client вернул None.")
        raise RuntimeError("Sheets client is None after init_sheets_client")

    # Создаём/проверяем структуру таблиц
    sc.ensure_structure()

    # --- Запуск бота ---
    if config.environment == "local":
        asyncio.run(run_polling(config))
    else:
        app = create_web_app(config)
        web.run_app(app, host="0.0.0.0", port=config.port)


if __name__ == "__main__":
    main()
