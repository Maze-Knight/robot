from __future__ import annotations

import asyncio
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class StoredPlayer:
    amae_player_id: str
    nickname: str | None
    source: str
    synced_at: str | None


@dataclass(frozen=True, slots=True)
class StoredProfile:
    amae_player_id: str
    nickname: str | None
    mode: str
    level_id: int | None
    level_score: int | None
    total_games: int | None
    average_rank: float | None
    negative_rate: float | None
    source: str
    source_record_id: str | None
    synced_at: str


class MajsoulDataRepository:
    """SQLite storage only; this class never contacts external providers."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    async def initialize(self) -> None:
        await asyncio.to_thread(self._initialize_sync)

    def _initialize_sync(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection, connection:
            # The service is intentionally single-process/local-first.  The
            # rollback journal avoids Windows file-handle issues during clean
            # shutdown while keeping SQLite's durable transactions.
            connection.execute("PRAGMA journal_mode=DELETE")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS players (
                    amae_player_id TEXT PRIMARY KEY,
                    nickname TEXT,
                    source TEXT NOT NULL,
                    source_player_id TEXT,
                    first_synced_at TEXT,
                    last_synced_at TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS player_profiles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    amae_player_id TEXT NOT NULL REFERENCES players(amae_player_id),
                    mode TEXT NOT NULL CHECK(mode IN ('four', 'three')),
                    nickname TEXT,
                    level_id INTEGER,
                    level_score INTEGER,
                    total_games INTEGER,
                    average_rank REAL,
                    negative_rate REAL,
                    rank_rates_json TEXT,
                    source TEXT NOT NULL,
                    source_record_id TEXT,
                    synced_at TEXT NOT NULL,
                    raw_payload_json TEXT,
                    UNIQUE(amae_player_id, mode)
                );
                CREATE TABLE IF NOT EXISTS game_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    amae_player_id TEXT NOT NULL REFERENCES players(amae_player_id),
                    mode TEXT NOT NULL CHECK(mode IN ('four', 'three')),
                    source TEXT NOT NULL,
                    source_record_id TEXT NOT NULL,
                    started_at TEXT,
                    placement INTEGER,
                    score INTEGER,
                    synced_at TEXT NOT NULL,
                    raw_payload_json TEXT,
                    UNIQUE(source, source_record_id)
                );
                CREATE TABLE IF NOT EXISTS sync_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    source TEXT,
                    requested_player_id TEXT,
                    cursor TEXT,
                    started_at TEXT,
                    finished_at TEXT,
                    last_error TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_profiles_player_mode
                    ON player_profiles(amae_player_id, mode);
                CREATE INDEX IF NOT EXISTS idx_records_player_mode
                    ON game_records(amae_player_id, mode, started_at DESC);
                """
            )

    async def health(self) -> bool:
        return await asyncio.to_thread(self._health_sync)

    def _health_sync(self) -> bool:
        try:
            with closing(self._connect()) as connection:
                connection.execute("SELECT 1").fetchone()
            return True
        except sqlite3.Error:
            return False

    async def get_player(self, amae_player_id: str) -> StoredPlayer | None:
        return await asyncio.to_thread(self._get_player_sync, amae_player_id)

    def _get_player_sync(self, amae_player_id: str) -> StoredPlayer | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT amae_player_id, nickname, source, last_synced_at FROM players WHERE amae_player_id=?",
                (amae_player_id,),
            ).fetchone()
        if row is None:
            return None
        return StoredPlayer(
            str(row["amae_player_id"]),
            str(row["nickname"]) if row["nickname"] is not None else None,
            str(row["source"]),
            str(row["last_synced_at"]) if row["last_synced_at"] is not None else None,
        )

    async def get_profile(self, amae_player_id: str, mode: str) -> StoredProfile | None:
        return await asyncio.to_thread(self._get_profile_sync, amae_player_id, mode)

    def _get_profile_sync(self, amae_player_id: str, mode: str) -> StoredProfile | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT p.amae_player_id, COALESCE(pp.nickname, p.nickname) AS nickname,
                       pp.mode, pp.level_id, pp.level_score, pp.total_games,
                       pp.average_rank, pp.negative_rate, pp.source,
                       pp.source_record_id, pp.synced_at
                FROM players p JOIN player_profiles pp ON pp.amae_player_id=p.amae_player_id
                WHERE p.amae_player_id=? AND pp.mode=?
                """,
                (amae_player_id, mode),
            ).fetchone()
        if row is None:
            return None
        return StoredProfile(
            amae_player_id=str(row["amae_player_id"]),
            nickname=str(row["nickname"]) if row["nickname"] is not None else None,
            mode=str(row["mode"]),
            level_id=int(row["level_id"]) if row["level_id"] is not None else None,
            level_score=int(row["level_score"]) if row["level_score"] is not None else None,
            total_games=int(row["total_games"]) if row["total_games"] is not None else None,
            average_rank=float(row["average_rank"]) if row["average_rank"] is not None else None,
            negative_rate=float(row["negative_rate"]) if row["negative_rate"] is not None else None,
            source=str(row["source"]),
            source_record_id=str(row["source_record_id"]) if row["source_record_id"] is not None else None,
            synced_at=str(row["synced_at"]),
        )
