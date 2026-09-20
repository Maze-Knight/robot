from __future__ import annotations

from typing import Protocol


class MajsoulDataProvider(Protocol):
    """A future, explicitly authorized source of locally stored Majsoul data."""

    name: str

    async def sync_player(self, amae_player_id: str) -> None:
        """Synchronize one player only when an approved provider is installed."""


class EmptyProvider:
    """Deliberately performs no network access and creates no player records."""

    name = "empty"

    async def sync_player(self, amae_player_id: str) -> None:
        del amae_player_id
        return None
