import asyncio
import logging
import os
from typing import Optional

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from .bot import register_handlers
from .config import Config, load_config
from .sheets.client import init_sheets_client
from .sheets import get_sheets_client
from .utils.logger import setup_logging
from .utils.webhook import WEBHOOK_PATH, build_webhook_url

logger = logging.getLogger(__name__)


def create_bot(config: Config) -> Bot:
    """
    Создаёт экземпляр бота с нужными настройками по умолчанию.
    Для aiogram 3.7+ parse_mode передаём через DefaultBotProperties.
    """
    return Bot(
        token=config.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def create_dispatcher() -> Dispatcher:
    """
    Создаёт dispatcher с in-memory storage для FSM.
    """
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    register_handlers(dp)
    return dp


async def handle_webhook(request: web.Request) -> web.Response:
    """
    Обработчик webhook-запросов Telegram.
    Приходит JSON-апдейт, прокидываем его в Dispatcher.
    """
    from aiogram.types import Update  # импорт тут, чтобы не тянуть раньше времени

    app: web.Application = request.app
    bot: Bot = app["bot"]
    dp: Dispatcher = app["dp"]

    data = await request.json()
    update = Update.model_validate(data, context={"bot": bot})

    # Прокидываем апдейт в dispatcher
    await dp.feed_update(bot=bot, update=update)

    # Telegram ждёт ответ 200 OK
    return web.Response(text="OK")


def create_web_app(config: Config) -> web.Application:
    """
    Собирает aiohttp-приложение для webhook-режима.
    """
    bot = create_bot(config)
    dp = create_dispatcher()

    app = web.Application()
    app["bot"] = bot
    app["dp"] = dp
    app["config"] = config

    # Путь вебхука и полный URL
    webhook_path = WEBHOOK_PATH  # например, "/tg/webhook/<секрет>"
    webhook_url = build_webhook_url(config.railway_public_domain)

    async def on_startup(app_: web.Application) -> None:
        """
        Старт приложения: ставим webhook.
        Никаких dp.startup(...) тут вызывать не нужно.
        """
        _bot: Bot = app_["bot"]
        _config: Config = app_["config"]

        logger.info(
            "Setting webhook: %s",
            webhook_url,
        )

        # Можно добавить drop_pending_updates=True, если хочется чистый старт
        await _bot.set_webhook(
            url=webhook_url,
            drop_pending_updates=True,
        )

    async def on_shutdown(app_: web.Application) -> None:
        """
        Остановка приложения: снимаем webhook и закрываем сессию бота.
        dp.shutdown() в таком ручном варианте вызывать не обязательно.
        """
        _bot: Bot = app_["bot"]

        try:
            await _bot.delete_webhook(drop_pending_updates=False)
        except Exception as e:
            logger.warning("Failed to delete webhook: %s", e)

        # Корректно закрываем HTTP-сессию бота
        await _bot.session.close()

    # Регистрируем хуки старта/остановки aiohttp-приложения
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)

    # Маршрут для Telegram webhook
    app.router.add_post(webhook_path, handle_webhook)

    return app


async def run_polling(config: Config) -> None:
    """
    Локальный режим: запускаем бота в long polling.
    """
    bot = create_bot(config)
    dp = create_dispatcher()

    logger.info("Starting bot in polling mode...")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


def main() -> None:
    """
    Точка входа приложения.
    В зависимости от ENVIRONMENT запускаем polling (local)
    или webhook (production).
    """
    setup_logging()

    try:
        config: Config = load_config()
    except Exception:
        logger.exception("Ошибка загрузки конфигурации, проверь переменные окружения.")
        raise

    # Инициализируем Google Sheets-клиент и структуру таблиц
    init_sheets_client(config)
    sheets_client = get_sheets_client()
    if sheets_client is None:
        logger.error("Sheets client глобально не инициализировался.")
        raise RuntimeError("Sheets client is None after init_sheets_client")

    logger.info("ENVIRONMENT=%s", config.environment)

    if config.environment.lower() == "production":
        # Webhook-режим
        app = create_web_app(config)
        port: int = config.port or int(os.getenv("PORT", "8000"))
        logger.info("Starting webhook server on 0.0.0.0:%s", port)
        web.run_app(app, host="0.0.0.0", port=port)
    else:
        # Локальный polling
        asyncio.run(run_polling(config))


if __name__ == "__main__":
    main()
