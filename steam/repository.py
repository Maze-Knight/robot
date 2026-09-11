from __future__ import annotations

import asyncio
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from .models import OfficialIdentity, SteamBinding


class SteamRepository:
    """Separate storage for QQ Official IDs; legacy QQ mappings stay untouched."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    async def initialize(self) -> None:
        await asyncio.to_thread(self._initialize_sync)

    def _initialize_sync(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection, connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS steam_platform_bindings (
                    platform TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    group_id TEXT NOT NULL DEFAULT '',
                    steam_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (platform, user_id, group_id)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS steam_presence_observations (
                    platform TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    group_id TEXT NOT NULL DEFAULT '',
                    game_id TEXT NOT NULL DEFAULT '',
                    observed_since TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (platform, user_id, group_id)
                )
                """
            )

    async def get_binding(self, identity: OfficialIdentity) -> SteamBinding | None:
        return await asyncio.to_thread(self._get_binding_sync, identity)

    def _get_binding_sync(self, identity: OfficialIdentity) -> SteamBinding | None:
        with closing(self._connect()) as connection, connection:
            row = connection.execute(
                "SELECT steam_id, created_at, updated_at FROM steam_platform_bindings "
                "WHERE platform = ? AND user_id = ? AND group_id = ?",
                (identity.platform, identity.user_id, identity.group_id),
            ).fetchone()
        if row is None:
            return None
        return SteamBinding(
            identity, str(row["steam_id"]),
            datetime.fromisoformat(str(row["created_at"])),
            datetime.fromisoformat(str(row["updated_at"])),
        )

    async def save_binding(self, identity: OfficialIdentity, steam_id: str) -> SteamBinding:
        await asyncio.to_thread(self._save_binding_sync, identity, steam_id)
        binding = await self.get_binding(identity)
        assert binding is not None
        return binding

    def _save_binding_sync(self, identity: OfficialIdentity, steam_id: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                INSERT INTO steam_platform_bindings
                    (platform, user_id, group_id, steam_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(platform, user_id, group_id) DO UPDATE SET
                    steam_id = excluded.steam_id, updated_at = excluded.updated_at
                """,
                (identity.platform, identity.user_id, identity.group_id, steam_id, now, now),
            )

    async def delete_binding(self, identity: OfficialIdentity) -> bool:
        return await asyncio.to_thread(self._delete_binding_sync, identity)

    def _delete_binding_sync(self, identity: OfficialIdentity) -> bool:
        with closing(self._connect()) as connection, connection:
            cursor = connection.execute(
                "DELETE FROM steam_platform_bindings "
                "WHERE platform = ? AND user_id = ? AND group_id = ?",
                (identity.platform, identity.user_id, identity.group_id),
            )
            connection.execute(
                "DELETE FROM steam_presence_observations "
                "WHERE platform = ? AND user_id = ? AND group_id = ?",
                (identity.platform, identity.user_id, identity.group_id),
            )
        return cursor.rowcount > 0

    async def observe_game(self, identity: OfficialIdentity, game_id: str) -> datetime | None:
        return await asyncio.to_thread(self._observe_game_sync, identity, game_id)

    def _observe_game_sync(self, identity: OfficialIdentity, game_id: str) -> datetime | None:
        now = datetime.now(timezone.utc)
        key = (identity.platform, identity.user_id, identity.group_id)
        with closing(self._connect()) as connection, connection:
            row = connection.execute(
                "SELECT game_id, observed_since FROM steam_presence_observations "
                "WHERE platform = ? AND user_id = ? AND group_id = ?", key
            ).fetchone()
            if not game_id:
                connection.execute(
                    "DELETE FROM steam_presence_observations "
                    "WHERE platform = ? AND user_id = ? AND group_id = ?", key
                )
                return None
            if row is not None and str(row["game_id"]) == game_id:
                connection.execute(
                    "UPDATE steam_presence_observations SET updated_at = ? "
                    "WHERE platform = ? AND user_id = ? AND group_id = ?",
                    (now.isoformat(), *key),
                )
                return datetime.fromisoformat(str(row["observed_since"]))
            connection.execute(
                """
                INSERT INTO steam_presence_observations
                    (platform, user_id, group_id, game_id, observed_since, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(platform, user_id, group_id) DO UPDATE SET
                    game_id = excluded.game_id,
                    observed_since = excluded.observed_since,
                    updated_at = excluded.updated_at
                """,
                (*key, game_id, now.isoformat(), now.isoformat()),
            )
            return now
