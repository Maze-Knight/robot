from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from fastapi.testclient import TestClient

from majsoul_data_service.app import create_app
from majsoul_data_service.database import MajsoulDataRepository
from majsoul_data_service.importer import import_local_file


class MajsoulDataServiceTests(unittest.TestCase):
    def make_client(self, directory: str) -> TestClient:
        return TestClient(create_app(Path(directory) / "service.sqlite3"))

    def test_health_initializes_sqlite_and_reports_empty_provider(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "service.sqlite3"
            with TestClient(create_app(database)) as client:
                response = client.get("/health")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["status"], "ok")
            self.assertEqual(response.json()["database"], "ok")
            self.assertEqual(response.json()["provider"], "empty")
            self.assertTrue(database.exists())

    def test_sqlite_initialization_creates_required_tables(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "service.sqlite3"
            import asyncio

            asyncio.run(MajsoulDataRepository(database).initialize())
            with closing(sqlite3.connect(database)) as connection, connection:
                names = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
            self.assertTrue(
                {"players", "player_profiles", "game_records", "sync_jobs"}.issubset(names)
            )

    def test_empty_database_player_is_explicitly_not_synced(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.make_client(directory) as client:
                response = client.get("/v1/players/amae-empty")
            self.assertEqual(response.status_code, 404)
            self.assertEqual(response.json()["detail"]["code"], "not_synced")

    def test_four_and_three_profiles_use_stable_mode_parameter(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.make_client(directory) as client:
                for mode in ("four", "three"):
                    response = client.get(f"/v1/players/amae-empty/profile?mode={mode}")
                    self.assertEqual(response.status_code, 404)
                    self.assertEqual(response.json()["detail"]["mode"], mode)

    def test_invalid_mode_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.make_client(directory) as client:
                response = client.get("/v1/players/amae-empty/profile?mode=two")
            self.assertEqual(response.status_code, 422)

    def test_missing_mode_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.make_client(directory) as client:
                response = client.get("/v1/players/amae-empty/profile")
            self.assertEqual(response.status_code, 422)

    def test_invalid_player_id_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.make_client(directory) as client:
                response = client.get("/v1/players/not%20an%20id")
            self.assertEqual(response.status_code, 422)
            self.assertEqual(response.json()["detail"]["code"], "invalid_player_id")

    def test_seeded_profile_returns_dto_without_dataclass_introspection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "service.sqlite3"
            with TestClient(create_app(database)) as client:
                repository = client.app.state.repository
                with closing(sqlite3.connect(database)) as connection, connection:
                    connection.execute(
                        "INSERT INTO players (amae_player_id, nickname, source, last_synced_at) "
                        "VALUES (?, ?, ?, ?)",
                        ("seeded", "测试玩家", "local", "2026-09-20T00:00:00Z"),
                    )
                    connection.execute(
                        "INSERT INTO player_profiles "
                        "(amae_player_id, mode, nickname, level_id, level_score, total_games, "
                        "average_rank, negative_rate, source, source_record_id, synced_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            "seeded",
                            "four",
                            "测试玩家",
                            7,
                            1234,
                            42,
                            2.1,
                            0.25,
                            "local",
                            "record-1",
                            "2026-09-20T00:00:00Z",
                        ),
                    )
                    connection.commit()
                self.assertIsNotNone(repository)
                response = client.get("/v1/players/seeded/profile?mode=four")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["mode"], "four")
            self.assertEqual(response.json()["total_games"], 42)

    def test_local_import_is_idempotent_and_serves_search_profile_records(self) -> None:
        import asyncio
        import json

        payload = {
            "source": "test_fixture_local_file",
            "players": [{
                "amae_player_id": "local-test-player",
                "nickname": "本地测试玩家",
                "profiles": [{
                    "mode": "four", "level_id": 10401, "level_score": 900,
                    "total_games": 12, "average_rank": 2.25, "negative_rate": 0.1,
                    "rank_rates": [0.3, 0.3, 0.2, 0.2],
                    "extended_stats": {"和牌率": 0.2}, "source_record_id": "profile-test",
                }],
                "game_records": [{
                    "mode": "four", "mode_id": 12, "source_record_id": "game-test-1",
                    "started_at": "2026-09-20T00:00:00+00:00", "placement": 1,
                    "score": 42000, "players": [{"accountId": "local-test-player", "score": 42000}],
                }],
            }],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "authorized-local-export.json"
            source.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            database = root / "service.sqlite3"
            repository = MajsoulDataRepository(database)
            asyncio.run(repository.initialize())
            first = asyncio.run(import_local_file(repository, source))
            second = asyncio.run(import_local_file(repository, source))
            with TestClient(create_app(database)) as client:
                search = client.get("/v1/players/search?nickname=本地测试")
                profile = client.get("/v1/players/local-test-player/profile?mode=four")
                records = client.get("/v1/players/local-test-player/records?mode=four")
        self.assertEqual((first.players, first.profiles, first.records), (1, 1, 1))
        self.assertEqual((second.players, second.profiles, second.records), (1, 1, 1))
        self.assertEqual(search.status_code, 200)
        self.assertEqual(search.json()[0]["amae_player_id"], "local-test-player")
        self.assertEqual(profile.json()["extended_stats"]["和牌率"], 0.2)
        self.assertEqual(records.json()[0]["source_record_id"], "game-test-1")


if __name__ == "__main__":
    unittest.main()
