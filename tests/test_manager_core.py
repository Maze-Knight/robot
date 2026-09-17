from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import httpx

from manager import ManagerState, create_app
from manager_core import default_runtime_directory, find_repository, load_environment, save_environment


class ManagerCoreTests(unittest.TestCase):
    def test_runtime_defaults_to_dist_outside_deployment_folder(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.assertEqual(default_runtime_directory(root), root / "dist")
            (root / "ElenaBot.exe").touch()
            self.assertEqual(default_runtime_directory(root), root)

    def test_finds_git_repository_from_deployment_subdirectory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / ".git").mkdir()
            deployment = root / "dist" / "nested"
            deployment.mkdir(parents=True)
            self.assertEqual(find_repository(deployment), root)

    def test_environment_update_preserves_unknown_settings(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / ".env"
            path.write_text("# keep\nQQ_APP_ID=old\nUNRELATED=value\n", "utf-8")
            save_environment(path, {"QQ_APP_ID": "new", "TRICKCAL_WEB_SESSION_DAYS": "30"})
            raw = path.read_text("utf-8")
            self.assertIn("# keep", raw)
            self.assertIn("UNRELATED=value", raw)
            self.assertEqual(load_environment(path)["QQ_APP_ID"], "new")
            self.assertEqual(load_environment(path)["TRICKCAL_WEB_SESSION_DAYS"], "30")

    def test_management_console_refuses_api_without_local_session(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            app = create_app(ManagerState(Path(temporary)))

            async def check() -> int:
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app),
                    base_url="http://127.0.0.1:8090",
                ) as client:
                    return (await client.get("/api/state")).status_code

            import asyncio
            self.assertEqual(asyncio.run(check()), 401)
