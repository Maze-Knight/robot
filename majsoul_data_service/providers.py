from __future__ import annotations

from typing import Any, Protocol


class MajsoulDataProvider(Protocol):
    """A future, explicitly authorized source of locally stored Majsoul data."""

    name: str

    async def search_player(self, nickname: str) -> tuple[dict[str, Any], ...]: ...

    async def fetch_player_profile(self, player_id: str, mode: str) -> dict[str, Any] | None: ...

    async def fetch_recent_games(self, player_id: str, mode: str) -> tuple[dict[str, Any], ...]: ...

    async def sync_player(self, amae_player_id: str) -> None: ...


class EmptyProvider:
    """Deliberately performs no network access and creates no player records."""

    name = "empty"

    async def search_player(self, nickname: str) -> tuple[dict[str, Any], ...]:
        del nickname
        return ()

    async def fetch_player_profile(self, player_id: str, mode: str) -> dict[str, Any] | None:
        del player_id, mode
        return None

    async def fetch_recent_games(self, player_id: str, mode: str) -> tuple[dict[str, Any], ...]:
        del player_id, mode
        return ()

    async def sync_player(self, amae_player_id: str) -> None:
        del amae_player_id
        return None


class LocalFileProvider(EmptyProvider):
    """Marker provider for data that arrived through the explicit local importer."""

    name = "local_file"
