from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

import httpx

from .models import SteamPlayer


logger = logging.getLogger("elena.qq.steam")
STEAM_ID64_BASE = 76561197960265728
_STEAM_ID64_RE = re.compile(r"^7656119\d{10}$")
_PROFILE_RE = re.compile(r"steamcommunity\.com/profiles/(7656119\d{10})", re.I)
_VANITY_RE = re.compile(r"steamcommunity\.com/id/([^/?#]+)", re.I)


class SteamError(RuntimeError):
    pass


class SteamConfigurationError(SteamError):
    pass


class SteamInputError(SteamError):
    pass


class SteamApiError(SteamError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class SteamClient:
    def __init__(
        self,
        http_client: httpx.AsyncClient,
        api_key: str,
        *,
        api_base: str = "https://api.steampowered.com",
        timeout: float = 15.0,
        retries: int = 2,
    ) -> None:
        self._http = http_client
        self._api_key = api_key
        self._api_base = api_base.rstrip("/")
        self._timeout = timeout
        self._retries = retries

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    def _require_key(self) -> None:
        if not self._api_key:
            raise SteamConfigurationError("STEAM_API_KEY is not configured")

    async def _request(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        self._require_key()
        request_params = {**params, "key": self._api_key}
        last_error: Exception | None = None
        for attempt in range(self._retries + 1):
            logger.info("[STEAM] request start | endpoint=%s | attempt=%s", path, attempt + 1)
            try:
                response = await self._http.get(
                    f"{self._api_base}{path}",
                    params=request_params,
                    timeout=self._timeout,
                )
                if response.status_code == 429:
                    raise SteamApiError("Steam API rate limited", status_code=429)
                if response.status_code in {401, 403}:
                    raise SteamApiError(
                        "Steam API authentication rejected", status_code=response.status_code
                    )
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise SteamApiError("Steam API returned a non-object payload")
                return payload
            except (httpx.TimeoutException, httpx.NetworkError, SteamApiError) as exc:
                last_error = exc
                if attempt < self._retries:
                    await asyncio.sleep(0.5 * (2**attempt))
                    continue
                if isinstance(exc, SteamApiError):
                    raise
                if isinstance(exc, httpx.TimeoutException):
                    raise SteamApiError("Steam API timeout") from exc
                raise SteamApiError("Steam API network failure") from exc
            except httpx.HTTPStatusError as exc:
                raise SteamApiError(
                    "Steam API HTTP failure", status_code=exc.response.status_code
                ) from exc
            except ValueError as exc:
                raise SteamApiError("Steam API returned invalid JSON") from exc
        raise SteamApiError("Steam API request failed") from last_error

    async def resolve_steam_id(self, raw: str) -> str:
        value = raw.strip().strip("<>")
        profile = _PROFILE_RE.search(value)
        if profile:
            return profile.group(1)
        if _STEAM_ID64_RE.fullmatch(value):
            return value
        if value.isdigit() and 1 <= len(value) <= 10:
            account_id = int(value)
            if 0 < account_id < 2**32:
                return str(STEAM_ID64_BASE + account_id)
        vanity_match = _VANITY_RE.search(value)
        if vanity_match:
            payload = await self._request(
                "/ISteamUser/ResolveVanityURL/v1/",
                {"vanityurl": vanity_match.group(1)},
            )
            result = payload.get("response", {})
            steam_id = str(result.get("steamid") or "") if isinstance(result, dict) else ""
            if isinstance(result, dict) and result.get("success") == 1 and _STEAM_ID64_RE.fullmatch(steam_id):
                return steam_id
        raise SteamInputError("invalid Steam identity input")

    async def fetch_player(self, steam_id: str) -> SteamPlayer:
        payload = await self._request(
            "/ISteamUser/GetPlayerSummaries/v2/", {"steamids": steam_id}
        )
        response = payload.get("response", {})
        players = response.get("players", []) if isinstance(response, dict) else []
        if not isinstance(players, list) or not players or not isinstance(players[0], dict):
            raise SteamInputError("Steam player was not found")
        player = players[0]
        logger.info("[STEAM] status fetched | steam_id=%s", steam_id)
        return SteamPlayer(
            steam_id=str(player.get("steamid") or steam_id),
            name=str(player.get("personaname") or "未知玩家"),
            persona_state=int(player.get("personastate") or 0),
            game_id=str(player.get("gameid") or ""),
            game_name=str(player.get("gameextrainfo") or ""),
            profile_url=str(player.get("profileurl") or ""),
            last_logoff=int(player["lastlogoff"]) if player.get("lastlogoff") else None,
        )

