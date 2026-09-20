from __future__ import annotations

import asyncio
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

from .models import MajsoulBinding, MajsoulIdentity, PlayerCandidate


class MajsoulRepository:
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
            connection.execute("""
                CREATE TABLE IF NOT EXISTS majsoul_bindings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    platform TEXT NOT NULL,
                    platform_user_id TEXT NOT NULL,
                    scene_type TEXT NOT NULL,
                    amae_player_id TEXT NOT NULL,
                    nickname TEXT NOT NULL,
                    level_id INTEGER NOT NULL DEFAULT 0,
                    mode_family TEXT NOT NULL DEFAULT 'four',
                    bound_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(platform, platform_user_id, scene_type)
                )
            """)

    async def get(self, identity: MajsoulIdentity) -> MajsoulBinding | None:
        return await asyncio.to_thread(self._get_sync, identity)

    def _get_sync(self, identity: MajsoulIdentity) -> MajsoulBinding | None:
        with closing(self._connect()) as connection:
            row = connection.execute("""
                SELECT platform,platform_user_id,scene_type,amae_player_id,nickname,
                       level_id,mode_family,bound_at,updated_at
                FROM majsoul_bindings WHERE platform=? AND platform_user_id=? AND scene_type=?
            """, (identity.platform, identity.platform_user_id, identity.scene_type)).fetchone()
        return self._row_to_binding(row) if row else None

    async def bind(self, identity: MajsoulIdentity, candidate: PlayerCandidate) -> MajsoulBinding:
        return await asyncio.to_thread(self._bind_sync, identity, candidate)

    def _bind_sync(self, identity: MajsoulIdentity, candidate: PlayerCandidate) -> MajsoulBinding:
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        with closing(self._connect()) as connection, connection:
            connection.execute("""
                INSERT INTO majsoul_bindings(platform,platform_user_id,scene_type,amae_player_id,nickname,level_id,mode_family,bound_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?)
                ON CONFLICT(platform,platform_user_id,scene_type) DO UPDATE SET
                    amae_player_id=excluded.amae_player_id, nickname=excluded.nickname,
                    level_id=excluded.level_id, mode_family=excluded.mode_family, updated_at=excluded.updated_at
            """, (identity.platform, identity.platform_user_id, identity.scene_type, candidate.player_id, candidate.nickname, candidate.level_id, candidate.mode_family, now, now))
        result = self._get_sync(identity)
        assert result is not None
        return result

    async def unbind(self, identity: MajsoulIdentity) -> bool:
        return await asyncio.to_thread(self._unbind_sync, identity)

    def _unbind_sync(self, identity: MajsoulIdentity) -> bool:
        with closing(self._connect()) as connection, connection:
            cursor = connection.execute("DELETE FROM majsoul_bindings WHERE platform=? AND platform_user_id=? AND scene_type=?", (identity.platform, identity.platform_user_id, identity.scene_type))
            return cursor.rowcount > 0

    @staticmethod
    def _row_to_binding(row: sqlite3.Row) -> MajsoulBinding:
        return MajsoulBinding(MajsoulIdentity(str(row["platform"]), str(row["platform_user_id"]), str(row["scene_type"])), str(row["amae_player_id"]), str(row["nickname"]), int(row["level_id"]), str(row["mode_family"]), str(row["bound_at"]), str(row["updated_at"]))
