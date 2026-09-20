"""Client for Elena's local Majsoul data service.

It deliberately has no fallback to amae-koromo: when self_hosted is selected,
an unavailable local service remains unavailable instead of silently querying a
third party.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from .client import (
    MajsoulInvalidResponseError,
    MajsoulNotFoundError,
    MajsoulTimeoutError,
    MajsoulUnavailableError,
)
from .models import MajsoulStats, PlayerCandidate, RecentGame


class SelfHostedMajsoulClient:
    def __init__(self, http_client: httpx.AsyncClient, *, base_url: str) -> None:
        self._http = http_client
        self._base_url = base_url.rstrip("/")
        self._timeout = httpx.Timeout(8.0, connect=3.0)

    async def health(self) -> bool:
        try:
            response = await self._http.get(f"{self._base_url}/health", timeout=self._timeout)
            return response.status_code == 200 and response.json().get("status") == "ok"
        except (httpx.RequestError, ValueError):
            return False

    async def search_players(self, nickname: str) -> tuple[PlayerCandidate, ...]:
        payload = await self._get("/v1/players/search", params={"nickname": nickname})
        if not isinstance(payload, list):
            raise MajsoulInvalidResponseError("self-hosted search response is malformed")
        candidates: list[PlayerCandidate] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            try:
                candidates.append(PlayerCandidate(str(item["amae_player_id"]), str(item["nickname"]), int(item["level_id"]), int(item.get("latest_timestamp", 0)), str(item["mode"])))
            except (KeyError, TypeError, ValueError):
                continue
        return tuple(candidates)

    async def get_stats(self, player_id: str, mode_family: str) -> MajsoulStats:
        payload = await self._get(f"/v1/players/{player_id}/profile", params={"mode": mode_family})
        if not isinstance(payload, dict):
            raise MajsoulInvalidResponseError("self-hosted profile response is malformed")
        try:
            extended = payload.get("extended_stats", {})
            return MajsoulStats(
                nickname=str(payload.get("nickname") or ""),
                level_id=int(payload["level_id"]),
                level_score=int(payload.get("level_score") or 0),
                total_games=int(payload.get("total_games") or 0),
                rank_rates=tuple(float(value) for value in payload.get("rank_rates", []) if isinstance(value, (int, float))),
                average_rank=self._number(payload.get("average_rank")),
                negative_rate=self._number(payload.get("negative_rate")),
                extended={str(key): value for key, value in extended.items() if isinstance(value, (int, float)) and not isinstance(value, bool)} if isinstance(extended, dict) else {},
                updated_at=self._time(payload.get("synced_at")),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise MajsoulInvalidResponseError("self-hosted profile fields are invalid") from exc

    async def get_recent_games(self, player_id: str, mode_family: str) -> tuple[RecentGame, ...]:
        payload = await self._get(f"/v1/players/{player_id}/records", params={"mode": mode_family, "limit": 20})
        if not isinstance(payload, list):
            raise MajsoulInvalidResponseError("self-hosted records response is malformed")
        games: list[RecentGame] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            try:
                games.append(RecentGame(int(item.get("mode_id") or 0), self._time(item.get("started_at")), self._integer(item.get("placement")), self._integer(item.get("score"))))
            except (TypeError, ValueError):
                continue
        return tuple(games)

    async def _get(self, path: str, *, params: dict[str, object]) -> Any:
        try:
            response = await self._http.get(f"{self._base_url}{path}", params=params, timeout=self._timeout)
        except httpx.TimeoutException as exc:
            raise MajsoulTimeoutError("self-hosted service timed out") from exc
        except httpx.RequestError as exc:
            raise MajsoulUnavailableError("self-hosted service request failed") from exc
        if response.status_code == 404:
            raise MajsoulNotFoundError("player data has not been synced")
        if response.is_error:
            raise MajsoulUnavailableError(f"self-hosted service HTTP {response.status_code}")
        try:
            return response.json()
        except ValueError as exc:
            raise MajsoulInvalidResponseError("self-hosted service returned invalid JSON") from exc

    @staticmethod
    def _number(value: object) -> float | None:
        return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None

    @staticmethod
    def _integer(value: object) -> int | None:
        return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None

    @staticmethod
    def _time(value: object) -> datetime | None:
        if not isinstance(value, str):
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
