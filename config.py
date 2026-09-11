from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_DIR = Path(__file__).resolve().parent


class ConfigurationError(RuntimeError):
    """Raised when required runtime configuration is missing."""


@dataclass(frozen=True, slots=True)
class Settings:
    app_id: str
    app_secret: str
    api_base: str
    token_url: str
    log_level: str
    steam_api_key: str
    steam_api_base: str
    steam_request_timeout: float
    steam_retry_times: int
    steam_monitor_enabled: bool

    def apply_sdk_environment(self) -> None:
        """Set SDK endpoint overrides before qqbot_agent_sdk is imported."""
        os.environ["QQ_API_BASE"] = self.api_base
        os.environ["QQ_TOKEN_URL"] = self.token_url


def load_settings() -> Settings:
    load_dotenv(PROJECT_DIR / ".env")

    app_id = os.getenv("QQ_APP_ID", "").strip()
    app_secret = os.getenv("QQ_APP_SECRET", "").strip()
    missing = [
        name
        for name, value in (
            ("QQ_APP_ID", app_id),
            ("QQ_APP_SECRET", app_secret),
        )
        if not value
    ]
    if missing:
        names = ", ".join(missing)
        raise ConfigurationError(
            f"缺少必填环境变量：{names}。请复制 .env.example 为 .env 并填写真实凭证。"
        )

    try:
        steam_timeout = float(os.getenv("STEAM_REQUEST_TIMEOUT", "15"))
        steam_retries = int(os.getenv("STEAM_RETRY_TIMES", "2"))
    except ValueError as exc:
        raise ConfigurationError(
            "STEAM_REQUEST_TIMEOUT 或 STEAM_RETRY_TIMES 格式无效。"
        ) from exc

    return Settings(
        app_id=app_id,
        app_secret=app_secret,
        api_base=os.getenv("QQ_API_BASE", "https://api.bot.qq.com").rstrip("/"),
        token_url=os.getenv(
            "QQ_TOKEN_URL", "https://api.bot.qq.com/app/getAppAccessToken"
        ),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        steam_api_key=os.getenv("STEAM_API_KEY", "").strip(),
        steam_api_base=os.getenv(
            "STEAM_API_BASE", "https://api.steampowered.com"
        ).rstrip("/"),
        steam_request_timeout=max(5.0, min(60.0, steam_timeout)),
        steam_retry_times=max(0, min(5, steam_retries)),
        steam_monitor_enabled=os.getenv("STEAM_MONITOR_ENABLED", "false")
        .strip()
        .casefold()
        in {"1", "true", "yes", "on"},
    )
