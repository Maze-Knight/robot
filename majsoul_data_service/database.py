from __future__ import annotations

import asyncio
import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
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
    rank_rates: tuple[float, ...] = ()
    extended_stats: dict[str, float | int] | None = None


@dataclass(frozen=True, slots=True)
class StoredRecord:
    source_record_id: str
    mode: str
    mode_id: int | None
    started_at: str | None
    placement: int | None
    score: int | None
    players: tuple[dict[str, Any], ...]


@dataclass(frozen=True, slots=True)
class StoredCandidate:
    amae_player_id: str
    nickname: str
    level_id: int
    mode: str
    latest_timestamp: int


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
            self._ensure_column(connection, "player_profiles", "extended_stats_json", "TEXT NOT NULL DEFAULT '{}'")
            self._ensure_column(connection, "game_records", "mode_id", "INTEGER")
            self._ensure_column(connection, "game_records", "players_json", "TEXT NOT NULL DEFAULT '[]'")

    @staticmethod
    def _ensure_column(connection: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        columns = {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}
        if column not in columns:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

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
                       pp.source_record_id, pp.synced_at, pp.rank_rates_json,
                       pp.extended_stats_json
                FROM players p JOIN player_profiles pp ON pp.amae_player_id=p.amae_player_id
                WHERE p.amae_player_id=? AND pp.mode=?
                """,
                (amae_player_id, mode),
            ).fetchone()
        if row is None:
            return None
        rates = self._number_tuple(row["rank_rates_json"])
        extended = self._number_map(row["extended_stats_json"])
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
            rank_rates=rates,
            extended_stats=extended,
        )

    @staticmethod
    def _number_tuple(raw: Any) -> tuple[float, ...]:
        try:
            parsed = json.loads(str(raw or "[]"))
            return tuple(float(value) for value in parsed if isinstance(value, (int, float)) and not isinstance(value, bool))
        except (TypeError, ValueError, json.JSONDecodeError):
            return ()

    @staticmethod
    def _number_map(raw: Any) -> dict[str, float | int]:
        try:
            parsed = json.loads(str(raw or "{}"))
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
        return {str(key): value for key, value in parsed.items() if isinstance(value, (int, float)) and not isinstance(value, bool)} if isinstance(parsed, dict) else {}

    async def search_players(self, nickname: str) -> tuple[StoredCandidate, ...]:
        return await asyncio.to_thread(self._search_players_sync, nickname)

    def _search_players_sync(self, nickname: str) -> tuple[StoredCandidate, ...]:
        query = nickname.strip()
        if not query:
            return ()
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """SELECT p.amae_player_id, p.nickname, pp.level_id, pp.mode,
                          COALESCE(strftime('%s', pp.synced_at), 0) AS latest_timestamp
                   FROM players p JOIN player_profiles pp ON pp.amae_player_id=p.amae_player_id
                   WHERE p.nickname LIKE ? OR pp.nickname LIKE ?
                   ORDER BY latest_timestamp DESC LIMIT 20""",
                (f"%{query}%", f"%{query}%"),
            ).fetchall()
        unique: dict[str, StoredCandidate] = {}
        for row in rows:
            player_id = str(row["amae_player_id"])
            unique.setdefault(player_id, StoredCandidate(player_id, str(row["nickname"] or ""), int(row["level_id"] or 0), str(row["mode"]), int(row["latest_timestamp"] or 0)))
        return tuple(unique.values())

    async def get_records(self, amae_player_id: str, mode: str, limit: int = 20) -> tuple[StoredRecord, ...]:
        return await asyncio.to_thread(self._get_records_sync, amae_player_id, mode, limit)

    def _get_records_sync(self, amae_player_id: str, mode: str, limit: int) -> tuple[StoredRecord, ...]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT source_record_id, mode, mode_id, started_at, placement, score, players_json FROM game_records WHERE amae_player_id=? AND mode=? ORDER BY started_at DESC LIMIT ?",
                (amae_player_id, mode, max(1, min(50, limit))),
            ).fetchall()
        records: list[StoredRecord] = []
        for row in rows:
            try:
                raw_players = json.loads(str(row["players_json"] or "[]"))
            except json.JSONDecodeError:
                raw_players = []
            players = tuple(item for item in raw_players if isinstance(item, dict)) if isinstance(raw_players, list) else ()
            records.append(StoredRecord(str(row["source_record_id"]), str(row["mode"]), int(row["mode_id"]) if row["mode_id"] is not None else None, str(row["started_at"]) if row["started_at"] is not None else None, int(row["placement"]) if row["placement"] is not None else None, int(row["score"]) if row["score"] is not None else None, players))
        return tuple(records)

    async def import_payload(self, payload: dict[str, Any], *, source_path: str) -> dict[str, int]:
        return await asyncio.to_thread(self._import_payload_sync, payload, source_path)

    def _import_payload_sync(self, payload: dict[str, Any], source_path: str) -> dict[str, int]:
        now = datetime.now(UTC).isoformat(timespec="seconds")
        source = str(payload.get("source") or "local_file").strip() or "local_file"
        players = payload.get("players")
        if not isinstance(players, list):
            raise ValueError("players must be a list")
        counts = {"players": 0, "profiles": 0, "records": 0}
        with closing(self._connect()) as connection, connection:
            job = connection.execute("INSERT INTO sync_jobs(provider_name,status,source,started_at) VALUES(?,?,?,?)", ("local_file", "running", source_path, now))
            job_id = int(job.lastrowid)
            try:
                for player in players:
                    if not isinstance(player, dict):
                        raise ValueError("each player must be an object")
                    player_id = str(player.get("amae_player_id") or "").strip()
                    nickname = str(player.get("nickname") or "").strip()
                    if not player_id or not nickname:
                        raise ValueError("each player needs amae_player_id and nickname")
                    connection.execute("""INSERT INTO players(amae_player_id,nickname,source,source_player_id,first_synced_at,last_synced_at)
                    VALUES(?,?,?,?,?,?) ON CONFLICT(amae_player_id) DO UPDATE SET nickname=excluded.nickname,source=excluded.source,last_synced_at=excluded.last_synced_at""", (player_id, nickname, source, player.get("source_player_id"), now, now))
                    counts["players"] += 1
                    profiles = player.get("profiles", [])
                    if not isinstance(profiles, list):
                        raise ValueError("profiles must be a list")
                    for profile in profiles:
                        if not isinstance(profile, dict) or profile.get("mode") not in {"four", "three"}:
                            raise ValueError("each profile needs mode=four or three")
                        mode = str(profile["mode"])
                        connection.execute("""INSERT INTO player_profiles(amae_player_id,mode,nickname,level_id,level_score,total_games,average_rank,negative_rate,rank_rates_json,extended_stats_json,source,source_record_id,synced_at,raw_payload_json)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(amae_player_id,mode) DO UPDATE SET nickname=excluded.nickname,level_id=excluded.level_id,level_score=excluded.level_score,total_games=excluded.total_games,average_rank=excluded.average_rank,negative_rate=excluded.negative_rate,rank_rates_json=excluded.rank_rates_json,extended_stats_json=excluded.extended_stats_json,source=excluded.source,source_record_id=excluded.source_record_id,synced_at=excluded.synced_at,raw_payload_json=excluded.raw_payload_json""", (player_id, mode, nickname, profile.get("level_id"), profile.get("level_score"), profile.get("total_games"), profile.get("average_rank"), profile.get("negative_rate"), json.dumps(profile.get("rank_rates", []), ensure_ascii=False), json.dumps(profile.get("extended_stats", {}), ensure_ascii=False), source, profile.get("source_record_id"), now, json.dumps(profile, ensure_ascii=False)))
                        counts["profiles"] += 1
                    records = player.get("game_records", [])
                    if not isinstance(records, list):
                        raise ValueError("game_records must be a list")
                    for record in records:
                        if not isinstance(record, dict) or record.get("mode") not in {"four", "three"} or not str(record.get("source_record_id") or "").strip():
                            raise ValueError("each record needs source_record_id and mode=four or three")
                        connection.execute("""INSERT INTO game_records(amae_player_id,mode,source,source_record_id,started_at,placement,score,mode_id,players_json,synced_at,raw_payload_json)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(source,source_record_id) DO UPDATE SET started_at=excluded.started_at,placement=excluded.placement,score=excluded.score,mode_id=excluded.mode_id,players_json=excluded.players_json,synced_at=excluded.synced_at,raw_payload_json=excluded.raw_payload_json""", (player_id, record["mode"], source, record["source_record_id"], record.get("started_at"), record.get("placement"), record.get("score"), record.get("mode_id"), json.dumps(record.get("players", []), ensure_ascii=False), now, json.dumps(record, ensure_ascii=False)))
                        counts["records"] += 1
                connection.execute("UPDATE sync_jobs SET status='completed', finished_at=? WHERE id=?", (now, job_id))
            except Exception as exc:
                connection.execute("UPDATE sync_jobs SET status='failed', finished_at=?, last_error=? WHERE id=?", (now, str(exc)[:500], job_id))
                raise
        return counts
