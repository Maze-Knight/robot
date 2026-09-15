from __future__ import annotations

import asyncio
import json
import sqlite3
from contextlib import closing
from pathlib import Path

from .models import DrawIdentity, DrawItem, DrawRecord


class DrawRepository:
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
                CREATE TABLE IF NOT EXISTS daily_draw_records (
                    platform TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    group_id TEXT NOT NULL DEFAULT '',
                    draw_date TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (platform, user_id, group_id, draw_date)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS daily_draw_collection (
                    platform TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    group_id TEXT NOT NULL DEFAULT '',
                    item_id TEXT NOT NULL,
                    copies INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (platform, user_id, group_id, item_id)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS daily_draw_collection_applied (
                    platform TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    group_id TEXT NOT NULL DEFAULT '',
                    draw_date TEXT NOT NULL,
                    PRIMARY KEY (platform, user_id, group_id, draw_date)
                )
                """
            )
            self._migrate_to_user_scope_sync(connection)
            self._backfill_collection_sync(connection)

    @staticmethod
    def _migrate_to_user_scope_sync(connection: sqlite3.Connection) -> None:
        """Preserve earlier group-scoped draws when moving to one collection per user."""
        rows = connection.execute(
            """
            SELECT platform,user_id,draw_date,result_json,created_at
            FROM daily_draw_records
            WHERE group_id <> ''
            ORDER BY created_at ASC
            """
        ).fetchall()
        for row in rows:
            connection.execute(
                """
                INSERT OR IGNORE INTO daily_draw_records
                    (platform,user_id,group_id,draw_date,result_json,created_at)
                VALUES (?,?, '',?,?,?)
                """,
                (
                    row["platform"], row["user_id"], row["draw_date"],
                    row["result_json"], row["created_at"],
                ),
            )

    @staticmethod
    def _backfill_collection_sync(connection: sqlite3.Connection) -> None:
        rows = connection.execute(
            """
            SELECT r.platform,r.user_id,r.group_id,r.draw_date,
                   r.result_json,r.created_at
            FROM daily_draw_records r
            LEFT JOIN daily_draw_collection_applied a
              ON a.platform=r.platform AND a.user_id=r.user_id
             AND a.group_id=r.group_id AND a.draw_date=r.draw_date
            WHERE a.draw_date IS NULL
            """
        ).fetchall()
        for row in rows:
            for item in json.loads(str(row["result_json"])):
                connection.execute(
                    """
                    INSERT INTO daily_draw_collection
                        (platform,user_id,group_id,item_id,copies,updated_at)
                    VALUES (?,?,?,?,1,?)
                    ON CONFLICT(platform,user_id,group_id,item_id) DO UPDATE SET
                        copies = copies + 1,
                        updated_at = excluded.updated_at
                    """,
                    (
                        row["platform"], row["user_id"], row["group_id"],
                        str(item["item_id"]), row["created_at"],
                    ),
                )
            connection.execute(
                "INSERT INTO daily_draw_collection_applied "
                "(platform,user_id,group_id,draw_date) VALUES (?,?,?,?)",
                (row["platform"], row["user_id"], row["group_id"], row["draw_date"]),
            )

    async def get(self, identity: DrawIdentity, draw_date: str) -> DrawRecord | None:
        return await asyncio.to_thread(self._get_sync, identity, draw_date)

    def _get_sync(self, identity: DrawIdentity, draw_date: str) -> DrawRecord | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT result_json, created_at FROM daily_draw_records "
                "WHERE platform=? AND user_id=? AND group_id=? AND draw_date=?",
                (identity.platform, identity.user_id, identity.group_id, draw_date),
            ).fetchone()
        if row is None:
            return None
        items = tuple(DrawItem(**item) for item in json.loads(row["result_json"]))
        return DrawRecord(identity, draw_date, items, str(row["created_at"]))

    async def save_if_absent(self, record: DrawRecord) -> tuple[DrawRecord, bool]:
        inserted = await asyncio.to_thread(self._save_if_absent_sync, record)
        stored = await self.get(record.identity, record.draw_date)
        assert stored is not None
        return stored, inserted

    def _save_if_absent_sync(self, record: DrawRecord) -> bool:
        payload = json.dumps(
            [
                {
                    "item_id": item.item_id,
                    "name": item.name,
                    "rarity": item.rarity,
                    "image": item.image,
                }
                for item in record.items
            ],
            ensure_ascii=False,
        )
        with closing(self._connect()) as connection, connection:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO daily_draw_records "
                "(platform,user_id,group_id,draw_date,result_json,created_at) "
                "VALUES (?,?,?,?,?,?)",
                (
                    record.identity.platform,
                    record.identity.user_id,
                    record.identity.group_id,
                    record.draw_date,
                    payload,
                    record.created_at,
                ),
            )
            if cursor.rowcount == 1:
                for item in record.items:
                    connection.execute(
                        """
                        INSERT INTO daily_draw_collection
                            (platform,user_id,group_id,item_id,copies,updated_at)
                        VALUES (?,?,?,?,1,?)
                        ON CONFLICT(platform,user_id,group_id,item_id) DO UPDATE SET
                            copies = copies + 1,
                            updated_at = excluded.updated_at
                        """,
                        (
                            record.identity.platform,
                            record.identity.user_id,
                            record.identity.group_id,
                            item.item_id,
                            record.created_at,
                        ),
                    )
                connection.execute(
                    "INSERT INTO daily_draw_collection_applied "
                    "(platform,user_id,group_id,draw_date) VALUES (?,?,?,?)",
                    (
                        record.identity.platform,
                        record.identity.user_id,
                        record.identity.group_id,
                        record.draw_date,
                    ),
                )
        return cursor.rowcount == 1

    async def get_collection_counts(self, identity: DrawIdentity) -> dict[str, int]:
        return await asyncio.to_thread(self._get_collection_counts_sync, identity)

    def _get_collection_counts_sync(self, identity: DrawIdentity) -> dict[str, int]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT item_id,copies FROM daily_draw_collection "
                "WHERE platform=? AND user_id=? AND group_id=?",
                (identity.platform, identity.user_id, identity.group_id),
            ).fetchall()
        return {str(row["item_id"]): int(row["copies"]) for row in rows}
