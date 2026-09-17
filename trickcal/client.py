"""Remote HTTPS client for the website-owned Trickcal module.

This module deliberately knows nothing about QQ menus, local SQLite, or the
legacy web session implementation.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from urllib.parse import urlsplit

import httpx

from .models import LoginTicketResponse, TrickcalIdentity, TrickcalSummary

logger = logging.getLogger("elena.qq.trickcal.client")


class TrickcalError(RuntimeError):
    """Base class for website API errors safe for interaction routing."""


class TrickcalUnavailableError(TrickcalError):
    pass


class TrickcalAuthError(TrickcalError):
    pass


class TrickcalTimeoutError(TrickcalError):
    pass


class TrickcalInvalidResponseError(TrickcalError):
    pass


class TrickcalRateLimitError(TrickcalError):
    pass


class TrickcalProfileNotFoundError(TrickcalError):
    pass


class TrickcalClient:
    """A shared-client, provisional-contract adapter for the Gift website."""

    def __init__(
        self,
        http_client: httpx.AsyncClient,
        *,
        api_base_url: str,
        bot_api_key: str,
    ) -> None:
        parsed = urlsplit(api_base_url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("TRICKCAL_API_BASE_URL 必须是没有账号信息的 HTTPS 地址。")
        self._http = http_client
        self._base_url = api_base_url.rstrip("/")
        self._trusted_host = parsed.hostname.casefold()
        self._api_key = bot_api_key
        self._timeout = httpx.Timeout(10.0, connect=5.0)

    @property
    def configured(self) -> bool:
        return bool(self._base_url and self._api_key)

    async def create_login_ticket(self, identity: TrickcalIdentity) -> LoginTicketResponse:
        # Ticket creation is intentionally not retried: the provisional API has
        # no idempotency key yet and retrying could create duplicate entries.
        payload = await self._post("/api/bot/tr-board/login-ticket", identity, retry=False, operation="login ticket")
        url = payload.get("url")
        if not isinstance(url, str) or not self._is_trusted_entry_url(url):
            raise TrickcalInvalidResponseError("login ticket URL is missing or untrusted")
        logger.info("[TRICKCAL] login ticket success")
        return LoginTicketResponse(url=url)

    async def get_summary(self, identity: TrickcalIdentity) -> TrickcalSummary:
        payload = await self._post("/api/bot/tr-board/summary", identity, retry=True, operation="summary")
        logger.info("[TRICKCAL] summary success")
        return TrickcalSummary.from_payload(payload)

    async def health_check(self) -> bool:
        """Check the website's public directory status without a QQ UI action."""
        if not self.configured:
            return False
        try:
            response = await self._http.get(
                self._base_url + "/api/bot/tr-board/status",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Accept": "application/json",
                    "User-Agent": "ElenaBot/1.0 TrickcalRemoteClient",
                },
                timeout=self._timeout,
            )
        except httpx.RequestError:
            logger.warning("[TRICKCAL] status request unavailable")
            return False
        return response.is_success

    async def _post(
        self,
        path: str,
        identity: TrickcalIdentity,
        *,
        retry: bool,
        operation: str,
    ) -> dict[str, Any]:
        if not self.configured:
            raise TrickcalUnavailableError("remote configuration is incomplete")
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/json",
            "User-Agent": "ElenaBot/1.0 TrickcalRemoteClient",
        }
        attempts = 2 if retry else 1
        for attempt in range(attempts):
            logger.info("[TRICKCAL] %s request", operation)
            try:
                response = await self._http.post(
                    self._base_url + path,
                    json=identity.to_payload(),
                    headers=headers,
                    timeout=self._timeout,
                )
            except httpx.TimeoutException as exc:
                logger.warning("[TRICKCAL] api timeout")
                if attempt + 1 < attempts:
                    await asyncio.sleep(0.15)
                    continue
                raise TrickcalTimeoutError("website API timed out") from exc
            except httpx.RequestError as exc:
                logger.warning("[TRICKCAL] api connection error | type=%s", type(exc).__name__)
                if attempt + 1 < attempts:
                    await asyncio.sleep(0.15)
                    continue
                raise TrickcalUnavailableError("website API connection failed") from exc

            if response.status_code in {502, 503, 504} and attempt + 1 < attempts:
                logger.warning("[TRICKCAL] api temporary failure | status=%s", response.status_code)
                await asyncio.sleep(0.15)
                continue
            return self._parse_response(response)
        raise TrickcalUnavailableError("website API unavailable")

    def _parse_response(self, response: httpx.Response) -> dict[str, Any]:
        if response.status_code in {401, 403}:
            logger.warning("[TRICKCAL] api unauthorized")
            raise TrickcalAuthError("website API authentication failed")
        if response.status_code == 429:
            logger.warning("[TRICKCAL] api rate limited")
            raise TrickcalRateLimitError("website API rate limited")
        if response.status_code >= 500:
            raise TrickcalUnavailableError(
                f"website API returned HTTP {response.status_code}"
            )
        try:
            raw = response.json()
        except ValueError as exc:
            raise TrickcalInvalidResponseError("website API did not return JSON") from exc
        if not isinstance(raw, dict):
            raise TrickcalInvalidResponseError("website API JSON root is not an object")

        if raw.get("ok") is False:
            self._raise_api_error(raw.get("error"))
        if response.is_error:
            raise TrickcalUnavailableError(f"website API returned HTTP {response.status_code}")

        payload = raw.get("data") if raw.get("ok") is True else raw
        if not isinstance(payload, dict):
            raise TrickcalInvalidResponseError("website API data is not an object")
        return payload

    @staticmethod
    def _raise_api_error(code: Any) -> None:
        if code == "unauthorized":
            raise TrickcalAuthError("website API authentication failed")
        if code == "rate_limited":
            raise TrickcalRateLimitError("website API rate limited")
        if code == "profile_not_found":
            raise TrickcalProfileNotFoundError("website profile not found")
        if code in {"identity_invalid", "ticket_create_failed", "internal_error"}:
            raise TrickcalUnavailableError("website API rejected the request")
        raise TrickcalInvalidResponseError("website API returned an unknown error")

    def _is_trusted_entry_url(self, value: str) -> bool:
        parsed = urlsplit(value)
        return bool(
            parsed.scheme == "https"
            and parsed.hostname
            and parsed.hostname.casefold() == self._trusted_host
            and not parsed.username
            and not parsed.password
        )
