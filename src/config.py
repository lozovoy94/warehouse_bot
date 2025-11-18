import os
import base64
import json
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class Config:
    telegram_bot_token: str
    google_sheet_id: str
    google_service_account_info: Dict[str, Any]
    timezone: str
    environment: str
    railway_public_domain: Optional[str]
    webhook_secret: str
    port: int


def _load_service_account_info(raw: str) -> Dict[str, Any]:
    """
    Безопасный вариант: в переменную окружения кладём base64-строку от JSON.
    Здесь:
    1) Пытаемся декодировать как base64 -> JSON.
    2) Если не получилось, считаем, что это уже JSON-строка.
    """
    try:
        decoded = base64.b64decode(raw).decode("utf-8")
        return json.loads(decoded)
    except Exception:
        # fallback: это просто JSON-строка
        return json.loads(raw)


def _compute_webhook_secret(bot_token: str) -> str:
    import hashlib

    return hashlib.sha256(bot_token.encode("utf-8")).hexdigest()[:32]


def load_config() -> Config:
    bot_token = os.environ["TELEGRAM_BOT_TOKEN"]
    google_sheet_id = os.environ["GOOGLE_SHEET_ID"]
    sa_raw = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]

    google_service_account_info = _load_service_account_info(sa_raw)

    timezone = os.environ.get("TIMEZONE", "Europe/Moscow")
    environment = os.environ.get("ENVIRONMENT", "local").lower()
    railway_public_domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN")
    port = int(os.environ.get("PORT", "8080"))

    webhook_secret = _compute_webhook_secret(bot_token)

    return Config(
        telegram_bot_token=bot_token,
        google_sheet_id=google_sheet_id,
        google_service_account_info=google_service_account_info,
        timezone=timezone,
        environment=environment,
        railway_public_domain=railway_public_domain,
        webhook_secret=webhook_secret,
        port=port,
    )
