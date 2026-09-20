from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

from runtime import APP_DIR

PROJECT_DIR = APP_DIR


class ConfigurationError(RuntimeError):
    """Raised when required runtime configuration is missing."""


@dataclass(frozen=True, slots=True)
class Settings:
    app_id: str
    app_secret: str
    api_base: str
    token_url: str
    log_level: str
    gift_api_base_url: str
    gift_request_timeout: float
    trickcal_mode: str
    trickcal_api_base_url: str
    trickcal_bot_api_key: str
    # Legacy/local-only settings.  Remote mode never reads or requires them.
    trickcal_web_public_url: str
    trickcal_web_secure_cookie: bool
    trickcal_web_session_days: int
    trickcal_login_ticket_minutes: int

    def apply_sdk_environment(self) -> None:
        """Set SDK endpoint overrides before qqbot_agent_sdk is imported."""
        os.environ["QQ_API_BASE"] = self.api_base
        os.environ["QQ_TOKEN_URL"] = self.token_url

    @property
    def trickcal_remote_configured(self) -> bool:
        return bool(self.trickcal_api_base_url and self.trickcal_bot_api_key)


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
        gift_timeout = float(os.getenv("GIFT_REQUEST_TIMEOUT", "15"))
        trickcal_session_days = int(os.getenv("TRICKCAL_WEB_SESSION_DAYS", "30"))
        trickcal_ticket_minutes = int(
            os.getenv("TRICKCAL_LOGIN_TICKET_MINUTES", "10")
        )
    except ValueError as exc:
        raise ConfigurationError(
            "GIFT_REQUEST_TIMEOUT、TRICKCAL_WEB_SESSION_DAYS 或 "
            "TRICKCAL_LOGIN_TICKET_MINUTES 格式无效。"
        ) from exc

    trickcal_mode = os.getenv("TRICKCAL_MODE", "remote").strip().casefold()
    if trickcal_mode not in {"remote", "local", "disabled"}:
        trickcal_mode = "disabled"

    return Settings(
        app_id=app_id,
        app_secret=app_secret,
        api_base=os.getenv("QQ_API_BASE", "https://api.bot.qq.com").rstrip("/"),
        token_url=os.getenv(
            "QQ_TOKEN_URL", "https://api.bot.qq.com/app/getAppAccessToken"
        ),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        gift_api_base_url=os.getenv("GIFT_API_BASE_URL", "").strip().rstrip("/"),
        gift_request_timeout=max(5.0, min(60.0, gift_timeout)),
        trickcal_mode=trickcal_mode,
        trickcal_api_base_url=os.getenv("TRICKCAL_API_BASE_URL", "").strip().rstrip("/"),
        trickcal_bot_api_key=os.getenv("TRICKCAL_BOT_API_KEY", "").strip(),
        trickcal_web_public_url=os.getenv(
            "TRICKCAL_WEB_PUBLIC_URL", "http://127.0.0.1:8080/tr-board/"
        ).strip(),
        trickcal_web_secure_cookie=os.getenv("TRICKCAL_WEB_SECURE_COOKIE", "false")
        .strip()
        .casefold()
        in {"1", "true", "yes", "on"},
        trickcal_web_session_days=max(1, min(90, trickcal_session_days)),
        trickcal_login_ticket_minutes=max(1, min(30, trickcal_ticket_minutes)),
    )
