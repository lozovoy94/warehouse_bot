import logging
import sys


def setup_logging() -> None:
    """Базовая настройка логгера для всего приложения."""
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
