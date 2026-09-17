from __future__ import annotations

# LEGACY LOCAL IMPLEMENTATION: loaded only when TRICKCAL_MODE=local.

import asyncio
import hashlib
import json
import secrets
import sqlite3
import time
from contextlib import closing
from pathlib import Path
from typing import Any

from .models import BoardProfile, PlatformIdentity


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class TrickcalRepository:
    """The sole persistence boundary used by both QQ and the web application."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=15)
        connection.row_factory = sqlite3.Row
        return connection

    async def initialize(self) -> None:
        await asyncio.to_thread(self._initialize_sync)

    def _initialize_sync(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as db, db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS platform_identity (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    platform TEXT NOT NULL,
                    platform_user_id TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    last_seen_at REAL NOT NULL,
                    UNIQUE(platform, platform_user_id)
                );
                CREATE TABLE IF NOT EXISTS board_profile (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    identity_id INTEGER NOT NULL UNIQUE REFERENCES platform_identity(id),
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS board_units (
                    profile_id INTEGER NOT NULL REFERENCES board_profile(id),
                    unit_id INTEGER NOT NULL,
                    updated_at REAL NOT NULL,
                    PRIMARY KEY(profile_id, unit_id)
                );
                CREATE TABLE IF NOT EXISTS board_nodes (
                    profile_id INTEGER NOT NULL REFERENCES board_profile(id),
                    node_id INTEGER NOT NULL,
                    state TEXT NOT NULL CHECK(state IN ('selected', 'planned')),
                    updated_at REAL NOT NULL,
                    PRIMARY KEY(profile_id, node_id)
                );
                CREATE TABLE IF NOT EXISTS web_login_ticket (
                    ticket_hash TEXT PRIMARY KEY,
                    identity_id INTEGER NOT NULL REFERENCES platform_identity(id),
                    expires_at REAL NOT NULL,
                    used_at REAL,
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS web_login_ticket_expiry ON web_login_ticket(expires_at);
                CREATE TABLE IF NOT EXISTS web_session (
                    token_hash TEXT PRIMARY KEY,
                    profile_id INTEGER NOT NULL REFERENCES board_profile(id),
                    csrf_token TEXT NOT NULL,
                    expires_at REAL NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS web_session_expiry ON web_session(expires_at);
                CREATE TABLE IF NOT EXISTS trickcal_catalog_cache (
                    cache_key TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    fetched_at REAL NOT NULL,
                    source_label TEXT NOT NULL
                );
                """
            )

    async def touch_identity(self, platform: str, platform_user_id: str) -> PlatformIdentity:
        return await asyncio.to_thread(self._touch_identity_sync, platform, platform_user_id)

    def _touch_identity_sync(self, platform: str, platform_user_id: str) -> PlatformIdentity:
        now = time.time()
        with closing(self._connect()) as db, db:
            db.execute(
                "INSERT INTO platform_identity(platform,platform_user_id,created_at,last_seen_at) VALUES(?,?,?,?) "
                "ON CONFLICT(platform,platform_user_id) DO UPDATE SET last_seen_at=excluded.last_seen_at",
                (platform, platform_user_id, now, now),
            )
            row = db.execute(
                "SELECT id,platform,platform_user_id FROM platform_identity WHERE platform=? AND platform_user_id=?",
                (platform, platform_user_id),
            ).fetchone()
        assert row is not None
        return PlatformIdentity(int(row["id"]), str(row["platform"]), str(row["platform_user_id"]))

    async def profile_for_identity(self, identity_id: int) -> BoardProfile | None:
        return await asyncio.to_thread(self._profile_for_identity_sync, identity_id)

    def _profile_for_identity_sync(self, identity_id: int) -> BoardProfile | None:
        with closing(self._connect()) as db:
            row = db.execute("SELECT id,identity_id FROM board_profile WHERE identity_id=?", (identity_id,)).fetchone()
        return None if row is None else BoardProfile(int(row["id"]), int(row["identity_id"]))

    def _ensure_profile(self, db: sqlite3.Connection, identity_id: int, now: float) -> BoardProfile:
        db.execute(
            "INSERT INTO board_profile(identity_id,created_at,updated_at) VALUES(?,?,?) "
            "ON CONFLICT(identity_id) DO UPDATE SET updated_at=excluded.updated_at",
            (identity_id, now, now),
        )
        row = db.execute("SELECT id,identity_id FROM board_profile WHERE identity_id=?", (identity_id,)).fetchone()
        assert row is not None
        return BoardProfile(int(row["id"]), int(row["identity_id"]))

    async def issue_ticket(self, identity: PlatformIdentity, minutes: int) -> str:
        return await asyncio.to_thread(self._issue_ticket_sync, identity.id, minutes)

    def _issue_ticket_sync(self, identity_id: int, minutes: int) -> str:
        now = time.time()
        token = secrets.token_urlsafe(32)
        with closing(self._connect()) as db, db:
            db.execute("DELETE FROM web_login_ticket WHERE expires_at<=? OR used_at IS NOT NULL", (now,))
            db.execute(
                "INSERT INTO web_login_ticket(ticket_hash,identity_id,expires_at,created_at) VALUES(?,?,?,?)",
                (_digest(token), identity_id, now + minutes * 60, now),
            )
        return token

    async def redeem_ticket(self, token: str, session_days: int) -> tuple[str, str] | None:
        return await asyncio.to_thread(self._redeem_ticket_sync, token, session_days)

    def _redeem_ticket_sync(self, token: str, session_days: int) -> tuple[str, str] | None:
        now = time.time()
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT identity_id FROM web_login_ticket WHERE ticket_hash=? AND used_at IS NULL AND expires_at>?",
                (_digest(token), now),
            ).fetchone()
            if row is None:
                return None
            changed = db.execute(
                "UPDATE web_login_ticket SET used_at=? WHERE ticket_hash=? AND used_at IS NULL",
                (now, _digest(token)),
            )
            if changed.rowcount != 1:
                return None
            profile = self._ensure_profile(db, int(row["identity_id"]), now)
            session = secrets.token_urlsafe(32)
            csrf = secrets.token_urlsafe(24)
            db.execute(
                "INSERT INTO web_session(token_hash,profile_id,csrf_token,expires_at,created_at) VALUES(?,?,?,?,?)",
                (_digest(session), profile.id, csrf, now + session_days * 86400, now),
            )
        return session, csrf

    async def get_session(self, token: str) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._get_session_sync, token)

    def _get_session_sync(self, token: str) -> dict[str, Any] | None:
        now = time.time()
        with closing(self._connect()) as db, db:
            db.execute("DELETE FROM web_session WHERE expires_at<=?", (now,))
            row = db.execute(
                "SELECT profile_id,csrf_token,expires_at FROM web_session WHERE token_hash=? AND expires_at>?",
                (_digest(token), now),
            ).fetchone()
        return None if row is None else dict(row)

    async def logout(self, token: str) -> None:
        await asyncio.to_thread(self._logout_sync, token)

    def _logout_sync(self, token: str) -> None:
        with closing(self._connect()) as db, db:
            db.execute("DELETE FROM web_session WHERE token_hash=?", (_digest(token),))

    async def board_data(self, profile_id: int) -> dict[str, set[int]]:
        return await asyncio.to_thread(self._board_data_sync, profile_id)

    def _board_data_sync(self, profile_id: int) -> dict[str, set[int]]:
        with closing(self._connect()) as db:
            units = {int(row[0]) for row in db.execute("SELECT unit_id FROM board_units WHERE profile_id=?", (profile_id,))}
            selected = {int(row[0]) for row in db.execute("SELECT node_id FROM board_nodes WHERE profile_id=? AND state='selected'", (profile_id,))}
            planned = {int(row[0]) for row in db.execute("SELECT node_id FROM board_nodes WHERE profile_id=? AND state='planned'", (profile_id,))}
        return {"units": units, "selected": selected, "planned": planned}

    async def set_unit(self, profile_id: int, unit_id: int, owned: bool) -> None:
        await asyncio.to_thread(self._set_unit_sync, profile_id, unit_id, owned)

    def _set_unit_sync(self, profile_id: int, unit_id: int, owned: bool) -> None:
        now = time.time()
        with closing(self._connect()) as db, db:
            if owned:
                db.execute("INSERT INTO board_units(profile_id,unit_id,updated_at) VALUES(?,?,?) ON CONFLICT(profile_id,unit_id) DO UPDATE SET updated_at=excluded.updated_at", (profile_id, unit_id, now))
            else:
                db.execute("DELETE FROM board_units WHERE profile_id=? AND unit_id=?", (profile_id, unit_id))

    async def set_all_units(self, profile_id: int, unit_ids: list[int]) -> None:
        await asyncio.to_thread(self._set_all_units_sync, profile_id, unit_ids)

    def _set_all_units_sync(self, profile_id: int, unit_ids: list[int]) -> None:
        now = time.time()
        with closing(self._connect()) as db, db:
            db.executemany("INSERT INTO board_units(profile_id,unit_id,updated_at) VALUES(?,?,?) ON CONFLICT(profile_id,unit_id) DO UPDATE SET updated_at=excluded.updated_at", ((profile_id, item, now) for item in unit_ids))

    async def set_node(self, profile_id: int, node_id: int, state: str | None) -> None:
        await asyncio.to_thread(self._set_node_sync, profile_id, node_id, state)

    def _set_node_sync(self, profile_id: int, node_id: int, state: str | None) -> None:
        with closing(self._connect()) as db, db:
            if state is None:
                db.execute("DELETE FROM board_nodes WHERE profile_id=? AND node_id=?", (profile_id, node_id))
            else:
                db.execute("INSERT INTO board_nodes(profile_id,node_id,state,updated_at) VALUES(?,?,?,?) ON CONFLICT(profile_id,node_id) DO UPDATE SET state=excluded.state,updated_at=excluded.updated_at", (profile_id, node_id, state, time.time()))

    async def replace_board(self, profile_id: int, units: list[int], selected: list[int], planned: list[int]) -> None:
        await asyncio.to_thread(self._replace_board_sync, profile_id, units, selected, planned)

    def _replace_board_sync(self, profile_id: int, units: list[int], selected: list[int], planned: list[int]) -> None:
        now = time.time()
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM board_units WHERE profile_id=?", (profile_id,))
            db.execute("DELETE FROM board_nodes WHERE profile_id=?", (profile_id,))
            db.executemany("INSERT INTO board_units(profile_id,unit_id,updated_at) VALUES(?,?,?)", ((profile_id, item, now) for item in units))
            db.executemany("INSERT INTO board_nodes(profile_id,node_id,state,updated_at) VALUES(?,?, 'selected',?)", ((profile_id, item, now) for item in selected))
            db.executemany("INSERT INTO board_nodes(profile_id,node_id,state,updated_at) VALUES(?,?, 'planned',?)", ((profile_id, item, now) for item in planned))

    async def get_cached_catalog(self) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._get_cached_catalog_sync)

    def _get_cached_catalog_sync(self) -> dict[str, Any] | None:
        with closing(self._connect()) as db:
            row = db.execute("SELECT payload,fetched_at,source_label FROM trickcal_catalog_cache WHERE cache_key='catalog-v1'").fetchone()
        if row is None:
            return None
        try:
            payload = json.loads(str(row["payload"]))
        except json.JSONDecodeError:
            return None
        return {"payload": payload, "fetched_at": float(row["fetched_at"]), "source_label": str(row["source_label"])}

    async def save_catalog(self, payload: dict[str, Any], source_label: str) -> None:
        await asyncio.to_thread(self._save_catalog_sync, payload, source_label)

    def _save_catalog_sync(self, payload: dict[str, Any], source_label: str) -> None:
        with closing(self._connect()) as db, db:
            db.execute("INSERT INTO trickcal_catalog_cache(cache_key,payload,fetched_at,source_label) VALUES('catalog-v1',?,?,?) ON CONFLICT(cache_key) DO UPDATE SET payload=excluded.payload,fetched_at=excluded.fetched_at,source_label=excluded.source_label", (json.dumps(payload, ensure_ascii=False, separators=(",", ":")), time.time(), source_label))
