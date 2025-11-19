from __future__ import annotations

import os
from dataclasses import dataclass


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Environment variable {name} is not set")
    return value


@dataclass
class AppConfig:
    telegram_bot_token: str
    google_service_account_json: str
    google_sheet_id: str
    timezone: str
    environment: str
    railway_public_domain: str | None

    @classmethod
    def from_env(cls) -> "AppConfig":
        return cls(
            telegram_bot_token=_require_env("TELEGRAM_BOT_TOKEN"),
            google_service_account_json=_require_env("GOOGLE_SERVICE_ACCOUNT_JSON"),
            google_sheet_id=_require_env("GOOGLE_SHEET_ID"),
            timezone=os.getenv("TIMEZONE", "Europe/Moscow"),
            environment=os.getenv("ENVIRONMENT", "production"),
            railway_public_domain=os.getenv("RAILWAY_PUBLIC_DOMAIN") or None,
        )
