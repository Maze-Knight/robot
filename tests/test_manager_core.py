from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx

from manager import ManagerState, create_app
from manager_core import (
    build_distribution,
    default_runtime_directory,
    find_repository,
    load_environment,
    save_environment,
)


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

    def test_one_click_update_pulls_builds_and_restarts_bot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / ".git").mkdir()
            runtime = root / "dist"
            runtime.mkdir()
            state = ManagerState(runtime)
            state.sessions = {"session": "csrf"}
            app = create_app(state)

            async def update() -> tuple[int, str]:
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app),
                    base_url="http://127.0.0.1:8090",
                    cookies={"elena_manager_session": "session"},
                ) as client:
                    response = await client.post(
                        "/api/update",
                        headers={"origin": "http://127.0.0.1:8090", "x-csrf-token": "csrf"},
                    )
                    return response.status_code, response.json()["output"]

            with (
                patch("manager.git_pull_fast_forward", return_value=(True, "Already up to date.")) as pull,
                patch("manager.build_distribution", return_value=(True, "Build complete.")) as build,
                patch("manager.launch_bot", return_value=object()) as launch,
            ):
                import asyncio
                status, output = asyncio.run(update())

            self.assertEqual(status, 200)
            self.assertIn("拉取、构建与机器人重启完成", output)
            pull.assert_called_once_with(root)
            build.assert_called_once_with(root, stage_manager=False)
            launch.assert_called_once_with(runtime)

    def test_manager_exposes_remote_trickcal_environment_keys(self) -> None:
        from manager_core import ENVIRONMENT_KEYS

        self.assertIn("TRICKCAL_MODE", ENVIRONMENT_KEYS)
        self.assertIn("TRICKCAL_API_BASE_URL", ENVIRONMENT_KEYS)
        self.assertIn("TRICKCAL_BOT_API_KEY", ENVIRONMENT_KEYS)

    def test_staged_build_uses_a_temporary_manager_name(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "build_exe.ps1").touch()
            completed = SimpleNamespace(returncode=0, stdout="Build complete", stderr="")
            with patch("manager_core.subprocess.run", return_value=completed) as run:
                ok, output = build_distribution(root, stage_manager=True)

            self.assertTrue(ok)
            self.assertEqual(output, "Build complete")
            command = run.call_args.args[0]
            self.assertIn("-SkipInstall", command)
            self.assertEqual(command[-2:], ["-ManagerName", "ElenaManager.next"])

    def test_safe_pull_accepts_a_clean_porcelain_status(self) -> None:
        from manager_core import git_pull_fast_forward

        with patch(
            "manager_core.run_git",
            side_effect=[(0, "（没有输出）"), (0, "Already up to date.")],
        ):
            ok, output = git_pull_fast_forward(Path("repository"))

        self.assertTrue(ok)
        self.assertEqual(output, "Already up to date.")
