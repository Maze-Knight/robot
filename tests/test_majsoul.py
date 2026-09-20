from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
from PIL import Image

from majsoul.client import (
    MajsoulClient,
    MajsoulInvalidResponseError,
    MajsoulRateLimitError,
    MajsoulTimeoutError,
)
from majsoul.commands import MajsoulController, parse_majsoul_command
from majsoul.models import (
    MajsoulIdentity,
    MajsoulPlayerCardData,
    MajsoulStats,
    PlayerCandidate,
    RecentGame,
)
from majsoul.renderer import MajsoulCardRenderer
from majsoul.repository import MajsoulRepository
from majsoul.service import MajsoulBindingNotFoundError


class MajsoulCommandTests(unittest.TestCase):
    def test_chinese_commands_and_mode_switches(self) -> None:
        self.assertEqual(parse_majsoul_command("雀魂"), ("profile", ""))
        self.assertEqual(parse_majsoul_command("/雀魂服务"), ("home", ""))
        self.assertEqual(parse_majsoul_command("/雀魂"), ("profile", ""))
        self.assertEqual(parse_majsoul_command("雀魂三麻"), ("profile", "three"))
        self.assertEqual(parse_majsoul_command("绑定雀魂 Maze围城"), ("bind", "Maze围城"))
        self.assertEqual(parse_majsoul_command("解绑雀魂"), ("unbind", ""))


class MajsoulRepositoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_group_and_c2c_bindings_are_isolated(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            repository = MajsoulRepository(Path(folder) / "majsoul.sqlite3")
            await repository.initialize()
            candidate = PlayerCandidate("123", "Maze围城", 103, 1, "four")
            group = MajsoulIdentity("qq_official", "same-openid", "group")
            c2c = MajsoulIdentity("qq_official", "same-openid", "c2c")
            await repository.bind(group, candidate)
            self.assertIsNotNone(await repository.get(group))
            self.assertIsNone(await repository.get(c2c))
            self.assertTrue(await repository.unbind(group))
            self.assertIsNone(await repository.get(group))


class MajsoulClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_rate_limit_is_typed_without_retry(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(429, request=request, text="x-cap-token-required")

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            client = MajsoulClient(http)
            with self.assertRaises(MajsoulRateLimitError):
                await client.search_players("Maze")
        self.assertEqual(calls, 2)

    async def test_search_is_cached_for_one_hour(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(200, request=request, json=[{"id": 1, "nickname": "Maze", "level": {"id": 103}, "latest_timestamp": 1}])

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            client = MajsoulClient(http)
            first = await client.search_players("Maze")
            second = await client.search_players("Maze")
        self.assertEqual(first, second)
        self.assertEqual(calls, 2)

    async def test_stats_and_recent_games_are_parsed(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if "player_stats/" in path:
                return httpx.Response(200, request=request, json={
                    "nickname": "Maze围城", "count": 154,
                    "level": {"id": 303, "score": 1100, "delta": 37},
                    "rank_rates": [.3442, .2987, .1883, .1688],
                    "avg_rank": 2.18, "negative_rate": .026,
                })
            if "player_extended_stats/" in path:
                return httpx.Response(200, request=request, json={
                    "和牌率": .317, "放铳率": .1263, "自摸率": .2744,
                    "副露率": .5375, "立直率": .2086, "平均打点": 5323,
                    "最大连庄": 3, "和了巡数": 12.6,
                })
            if "player_records/" in path:
                return httpx.Response(200, request=request, json=[{
                    "modeId": 12, "startTime": 1_700_000_000,
                    "players": [{"accountId": 7, "score": 44300}, {"accountId": 8, "score": 21100}],
                }])
            return httpx.Response(404, request=request)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            client = MajsoulClient(http)
            stats = await client.get_stats("7", "four")
            games = await client.get_recent_games("7", "four")
        self.assertEqual(stats.nickname, "Maze围城")
        self.assertEqual(stats.level_score, 1137)
        self.assertAlmostEqual(stats.rank_rates[0], 0.3442)
        self.assertAlmostEqual(float(stats.extended["和牌率"]), .317)
        self.assertEqual(games[0].rank, 1)
        self.assertEqual(games[0].mode_label, "玉之间")

    async def test_invalid_json_and_timeout_are_typed(self) -> None:
        def invalid_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, request=request, content=b"not-json")

        async with httpx.AsyncClient(transport=httpx.MockTransport(invalid_handler)) as http:
            client = MajsoulClient(http)
            with self.assertRaises(MajsoulInvalidResponseError):
                await client.search_players("Maze")

        def timeout_handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("slow", request=request)

        async with httpx.AsyncClient(transport=httpx.MockTransport(timeout_handler)) as http:
            client = MajsoulClient(http)
            with self.assertRaises(MajsoulTimeoutError):
                await client.search_players("Maze")


class MajsoulCardTests(unittest.TestCase):
    def test_card_renders_chinese_profile_and_recent_games(self) -> None:
        data = MajsoulPlayerCardData(
            "Maze围城", "123", "four",
            MajsoulStats("Maze围城", 103, 1137, 154, (0.3442, 0.2987, 0.1883, 0.1688), 2.18, 0.026, {"和牌率": .317, "放铳率": .1263, "自摸率": .2744, "副露率": .5375, "立直率": .2086, "平均打点": 5323, "最大连庄": 3, "和了巡数": 12.6}, None),
            (RecentGame(12, datetime.now().astimezone(), 1, 44300),) * 5,
            datetime.now().astimezone(),
        )
        rendered = MajsoulCardRenderer().render(data)
        with Image.open(__import__("io").BytesIO(rendered)) as image:
            self.assertEqual(image.size, (1080, 1540))
            self.assertEqual(image.format, "PNG")


class MajsoulControllerTests(unittest.IsolatedAsyncioTestCase):
    async def test_unbound_profile_shows_registration_home(self) -> None:
        service = type("Service", (), {"profile": AsyncMock(side_effect=MajsoulBindingNotFoundError("none"))})()
        menus = type("Menus", (), {"send_majsoul_home": AsyncMock(), "send_plain_text": AsyncMock()})()
        controller = MajsoulController(service, menus, object())
        context = type("Context", (), {"content": "雀魂", "scene_type": "group", "group_id": "group", "user_id": "member", "message_id": "message"})()
        self.assertTrue(await controller.handle_text(context))
        menus.send_majsoul_home.assert_awaited_once()
