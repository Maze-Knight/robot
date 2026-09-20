from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

import httpx

from .models import (
    FOUR_PLAYER_MODES,
    THREE_PLAYER_MODES,
    MajsoulStats,
    PlayerCandidate,
    RecentGame,
)


logger = logging.getLogger("elena.qq.majsoul.client")

_MIRRORS = ("https://5-data.amae-koromo.com", "https://1.data.amae-koromo.com")


class MajsoulError(RuntimeError):
    pass


class MajsoulRateLimitError(MajsoulError):
    pass


class MajsoulNotFoundError(MajsoulError):
    pass


class MajsoulTimeoutError(MajsoulError):
    pass


class MajsoulInvalidResponseError(MajsoulError):
    pass


class MajsoulUnavailableError(MajsoulError):
    pass


class MajsoulClient:
    """Small, cache-first adapter for the API used by amae-koromo's frontend."""

    def __init__(self, http_client: httpx.AsyncClient) -> None:
        self._http = http_client
        self._cache: dict[str, tuple[float, Any]] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._timeout = httpx.Timeout(12.0, connect=5.0)

    async def search_players(self, nickname: str) -> tuple[PlayerCandidate, ...]:
        name = nickname.strip()
        if not name:
            return ()
        key = f"search:{name.casefold()}"

        async def load() -> tuple[PlayerCandidate, ...]:
            results: list[PlayerCandidate] = []
            errors: list[MajsoulError] = []
            for family in ("four", "three"):
                try:
                    payload = await self._get_json(
                        family,
                        f"search_player/{quote(name, safe='')}?limit=20&tag=all",
                    )
                except MajsoulNotFoundError:
                    continue
                except MajsoulError as exc:
                    errors.append(exc)
                    continue
                if not isinstance(payload, list):
                    raise MajsoulInvalidResponseError("player search root is not a list")
                results.extend(
                    candidate
                    for candidate in (PlayerCandidate.from_payload(item, family) for item in payload)
                    if candidate is not None
                )
            if not results and errors:
                if any(isinstance(error, MajsoulRateLimitError) for error in errors):
                    raise MajsoulRateLimitError("player search rate limited")
                raise errors[0]
            unique = {candidate.player_id: candidate for candidate in results}
            return tuple(sorted(unique.values(), key=lambda item: item.latest_timestamp, reverse=True))

        return await self._cached(key, 3600.0, load)

    async def get_stats(self, player_id: str, mode_family: str) -> MajsoulStats:
        modes = self._modes(mode_family)
        now_ms = int(time.time() * 1000)
        params = f"{player_id}/1262304000000/{now_ms}?mode={'.'.join(map(str, modes))}&tag={int(time.time() // 3600)}"
        metadata = await self._cached(
            f"stats:{mode_family}:{player_id}", 480.0,
            lambda: self._get_json(mode_family, f"player_stats/{params}"),
        )
        extended = await self._cached(
            f"extended:{mode_family}:{player_id}", 480.0,
            lambda: self._get_json(mode_family, f"player_extended_stats/{params}"),
        )
        if not isinstance(metadata, dict) or not isinstance(extended, dict):
            raise MajsoulInvalidResponseError("player stats response is malformed")
        level = metadata.get("level")
        if not isinstance(level, dict):
            raise MajsoulInvalidResponseError("player level is missing")
        try:
            raw_rates = metadata.get("rank_rates", [])
            rates = tuple(float(value) for value in raw_rates if isinstance(value, (int, float)))
            rate_total = sum(rates)
            if rate_total > 1.5:
                rates = tuple(value / rate_total for value in rates) if rate_total else ()
            parsed_extended = {
                str(key): value
                for key, value in extended.items()
                if isinstance(value, (int, float)) and not isinstance(value, bool)
            }
            updated_at = self._parse_last_modified(metadata.get("_lastModified"))
            return MajsoulStats(
                nickname=str(metadata["nickname"]).strip(),
                level_id=int(level["id"]),
                level_score=int(float(level.get("score", 0)) + float(level.get("delta", 0))),
                total_games=int(metadata.get("count", 0)),
                rank_rates=rates,
                average_rank=self._number(metadata.get("avg_rank")),
                negative_rate=self._number(metadata.get("negative_rate")),
                extended=parsed_extended,
                updated_at=updated_at,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise MajsoulInvalidResponseError("player stats fields are invalid") from exc

    async def get_recent_games(self, player_id: str, mode_family: str) -> tuple[RecentGame, ...]:
        modes = self._modes(mode_family)
        now_ms = int(time.time() * 1000)
        path = f"player_records/{player_id}/{now_ms}/1262304000000?limit=20&mode={','.join(map(str, modes))}&descending=true"
        try:
            payload = await self._cached(
                f"records:{mode_family}:{player_id}", 180.0,
                lambda: self._get_json(mode_family, path),
            )
        except MajsoulNotFoundError:
            # The frontend also treats a missing records endpoint as an empty history.
            return ()
        if not isinstance(payload, list):
            raise MajsoulInvalidResponseError("player records root is not a list")
        games = tuple(self._parse_game(item, player_id) for item in payload)
        return tuple(game for game in games if game is not None)

    async def _cached(self, key: str, ttl: float, loader: Any) -> Any:
        now = time.monotonic()
        cached = self._cache.get(key)
        if cached and cached[0] > now:
            return cached[1]
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            cached = self._cache.get(key)
            if cached and cached[0] > time.monotonic():
                return cached[1]
            value = await loader()
            self._cache[key] = (time.monotonic() + ttl, value)
            return value

    async def _get_json(self, family: str, path: str) -> Any:
        prefix = "pl3" if family == "three" else "pl4"
        url = f"{_MIRRORS[0]}/api/v2/{prefix}/{path}"
        try:
            response = await self._http.get(
                url,
                headers={"Accept": "application/json", "User-Agent": "ElenaBot/1.0 MajsoulProfile"},
                timeout=self._timeout,
            )
        except httpx.TimeoutException as exc:
            logger.warning("[MAJSOUL] upstream timeout | family=%s", family)
            raise MajsoulTimeoutError("amae-koromo request timed out") from exc
        except httpx.RequestError as exc:
            logger.warning("[MAJSOUL] upstream request error | type=%s", type(exc).__name__)
            raise MajsoulUnavailableError("amae-koromo request failed") from exc
        if response.status_code == 429:
            logger.warning("[MAJSOUL] upstream rate limited")
            raise MajsoulRateLimitError("amae-koromo rate limited")
        if response.status_code == 404:
            raise MajsoulNotFoundError("player data not found")
        if response.status_code >= 500:
            raise MajsoulUnavailableError(f"amae-koromo HTTP {response.status_code}")
        if response.is_error:
            raise MajsoulUnavailableError(f"amae-koromo HTTP {response.status_code}")
        try:
            return response.json()
        except ValueError as exc:
            raise MajsoulInvalidResponseError("amae-koromo returned invalid JSON") from exc

    @staticmethod
    def _modes(family: str) -> tuple[int, ...]:
        return THREE_PLAYER_MODES if family == "three" else FOUR_PLAYER_MODES

    @staticmethod
    def _number(value: Any) -> float | None:
        if isinstance(value, bool):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _parse_last_modified(value: Any) -> datetime | None:
        return value if isinstance(value, datetime) else None

    @staticmethod
    def _parse_game(payload: Any, player_id: str) -> RecentGame | None:
        if not isinstance(payload, dict) or not isinstance(payload.get("players"), list):
            return None
        try:
            players = payload["players"]
            indexed = list(enumerate(players))
            indexed.sort(key=lambda item: (-int(item[1].get("score", 0)), item[0]))
            rank = next((index + 1 for index, (_, player) in enumerate(indexed) if str(player.get("accountId")) == str(player_id)), None)
            current = next((player for player in players if str(player.get("accountId")) == str(player_id)), None)
            started = datetime.fromtimestamp(int(payload.get("startTime", 0)), tz=UTC) if payload.get("startTime") else None
            return RecentGame(int(payload.get("modeId", 0)), started, rank, int(current.get("score")) if current else None)
        except (TypeError, ValueError, OSError):
            return None
