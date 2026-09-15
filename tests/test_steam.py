from __future__ import annotations

import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
from PIL import Image

from steam import copywriting as copy
from steam.client import SteamApiError, SteamClient, SteamInputError
from steam.card import SteamCardRenderer
from steam.commands import SteamController, parse_steam_command
from steam.models import OfficialIdentity, SteamPlayer
from steam.monitor import classify_game_transition
from steam.repository import SteamRepository
from steam.service import PlayerResult, SteamService


STEAM_ID = "76561198000000000"


def player() -> SteamPlayer:
    return SteamPlayer(
        steam_id=STEAM_ID,
        name="MayorTest",
        persona_state=1,
        game_id="730",
        game_name="Counter-Strike 2",
        profile_url="https://steamcommunity.com/profiles/" + STEAM_ID,
        avatar_url="https://avatars.example/player.jpg",
        last_logoff=None,
    )


class CommandParsingTests(unittest.TestCase):
    def test_supported_text_commands(self) -> None:
        self.assertEqual(parse_steam_command("steam"), ("home", ""))
        self.assertEqual(parse_steam_command("steam状态"), ("status", ""))
        self.assertEqual(parse_steam_command("我的steam"), ("profile", ""))
        self.assertEqual(
            parse_steam_command("绑定steam " + STEAM_ID), ("bind", STEAM_ID)
        )
        self.assertEqual(parse_steam_command("解绑steam"), ("unbind", ""))
        self.assertEqual(parse_steam_command("/我的档案"), ("profile", ""))
        self.assertEqual(parse_steam_command("/当前状态"), ("status", ""))
        self.assertEqual(parse_steam_command("/身份登记"), ("bind_guide", ""))
        self.assertEqual(parse_steam_command("/解除登记"), ("unbind", ""))
        self.assertIsNone(parse_steam_command("ping"))


class MonitorMigrationTests(unittest.TestCase):
    def test_start_exit_switch_and_fluctuation_are_preserved(self) -> None:
        self.assertEqual(
            classify_game_transition({"gameid": ""}, {"gameid": "730"}).kind,
            "start",
        )
        self.assertTrue(
            classify_game_transition({"gameid": "730"}, {"gameid": ""}).has_exit
        )
        switched = classify_game_transition(
            {"gameid": "730"},
            {"gameid": "570"},
            pending_quit={"570": {"quit_time": 900, "notified": False}},
            now=1000,
        )
        self.assertEqual(switched.kind, "switch")
        self.assertTrue(switched.has_start)
        self.assertTrue(switched.network_fluctuation)


class RepositoryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.repo = SteamRepository(Path(self.temp.name) / "steam.sqlite3")
        await self.repo.initialize()

    async def asyncTearDown(self) -> None:
        self.temp.cleanup()

    async def test_group_and_c2c_openids_are_isolated(self) -> None:
        group = OfficialIdentity("qq_official", "member-openid", "group-openid")
        c2c = OfficialIdentity("qq_official", "member-openid", "")
        await self.repo.save_binding(group, STEAM_ID)
        self.assertEqual((await self.repo.get_binding(group)).steam_id, STEAM_ID)
        self.assertIsNone(await self.repo.get_binding(c2c))

    async def test_unbind_removes_only_requested_identity(self) -> None:
        identity = OfficialIdentity("qq_official", "member-openid", "group-openid")
        await self.repo.save_binding(identity, STEAM_ID)
        self.assertTrue(await self.repo.delete_binding(identity))
        self.assertIsNone(await self.repo.get_binding(identity))
        self.assertFalse(await self.repo.delete_binding(identity))


class SteamClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_resolves_id64_friend_code_and_profile(self) -> None:
        client = SteamClient(AsyncMock(), "key")
        self.assertEqual(await client.resolve_steam_id(STEAM_ID), STEAM_ID)
        self.assertEqual(
            await client.resolve_steam_id("https://steamcommunity.com/profiles/" + STEAM_ID),
            STEAM_ID,
        )
        self.assertEqual(
            await client.resolve_steam_id("39734272"),
            str(76561197960265728 + 39734272),
        )

    async def test_invalid_steam_id(self) -> None:
        client = SteamClient(AsyncMock(), "key")
        with self.assertRaises(SteamInputError):
            await client.resolve_steam_id("not-a-steam-id")

    async def test_api_429_is_classified(self) -> None:
        response = httpx.Response(
            429, request=httpx.Request("GET", "https://api.steampowered.com/test")
        )
        http = SimpleNamespace(get=AsyncMock(return_value=response))
        client = SteamClient(http, "key", retries=0)
        with self.assertRaises(SteamApiError) as raised:
            await client.fetch_player(STEAM_ID)
        self.assertEqual(raised.exception.status_code, 429)

    async def test_api_timeout_is_classified(self) -> None:
        http = SimpleNamespace(get=AsyncMock(side_effect=httpx.ReadTimeout("slow")))
        client = SteamClient(http, "key", retries=0)
        with self.assertRaisesRegex(SteamApiError, "timeout"):
            await client.fetch_player(STEAM_ID)


class SteamServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.repo = SteamRepository(Path(self.temp.name) / "steam.sqlite3")
        await self.repo.initialize()
        self.client = SimpleNamespace(
            resolve_steam_id=AsyncMock(return_value=STEAM_ID),
            fetch_player=AsyncMock(return_value=player()),
        )
        self.service = SteamService(self.client, self.repo)
        self.identity = OfficialIdentity("qq_official", "member-openid", "group-openid")

    async def asyncTearDown(self) -> None:
        self.temp.cleanup()

    async def test_register_profile_status_and_unbind(self) -> None:
        registered = await self.service.register_identity(self.identity, STEAM_ID)
        self.assertEqual(registered.name, "MayorTest")
        result = await self.service.get_profile(self.identity)
        self.assertEqual(result.player.game_name, "Counter-Strike 2")
        self.assertIn("Steam 档案", copy.profile(result))
        self.assertIn("Steam 状态", copy.status(result))
        self.assertTrue(await self.service.unregister_identity(self.identity))
        self.assertIsNone(await self.service.get_profile(self.identity))


class SteamControllerTests(unittest.IsolatedAsyncioTestCase):
    async def test_group_text_status_uses_member_and_group_openids(self) -> None:
        service = SimpleNamespace(
            get_profile=AsyncMock(return_value=PlayerResult(player()))
        )
        menus = SimpleNamespace(send_steam_home=AsyncMock())
        controller = SteamController(service, menus)
        context = SimpleNamespace(
            content="steam状态",
            scene_type="group",
            group_id="group-openid",
            user_id="member-openid",
            message_id="message-id",
            reply=AsyncMock(),
        )
        self.assertTrue(await controller.handle_text(context))
        identity = service.get_profile.await_args.args[0]
        self.assertEqual(identity.user_id, "member-openid")
        self.assertEqual(identity.group_id, "group-openid")
        self.assertIn("Steam 状态", context.reply.await_args.args[0])

    async def test_status_uses_rendered_card_when_renderer_is_configured(self) -> None:
        result = PlayerResult(player())
        service = SimpleNamespace(get_profile=AsyncMock(return_value=result))
        menus = SimpleNamespace(send_image=AsyncMock())
        renderer = AsyncMock(return_value=b"png-card")
        controller = SteamController(service, menus, renderer)
        context = SimpleNamespace(
            content="/当前状态",
            scene_type="group",
            group_id="group-openid",
            user_id="member-openid",
            message_id="message-id",
            reply=AsyncMock(),
        )

        self.assertTrue(await controller.handle_text(context))

        renderer.assert_awaited_once_with("status", result)
        menus.send_image.assert_awaited_once_with(
            "group",
            "group-openid",
            b"png-card",
            reply_to="message-id",
            file_name="steam-status.png",
        )
        context.reply.assert_not_awaited()

    async def test_c2c_identity_has_no_group_id(self) -> None:
        service = SimpleNamespace(get_profile=AsyncMock(return_value=None))
        controller = SteamController(service, SimpleNamespace())
        context = SimpleNamespace(
            content="我的steam",
            scene_type="c2c",
            group_id=None,
            user_id="c2c-openid",
            message_id="message-id",
            reply=AsyncMock(),
        )
        self.assertTrue(await controller.handle_text(context))
        identity = service.get_profile.await_args.args[0]
        self.assertEqual(identity.user_id, "c2c-openid")
        self.assertEqual(identity.group_id, "")
        self.assertEqual(context.reply.await_args.args[0], copy.NOT_BOUND)

    async def test_steam_interaction_routes_without_button_label_matching(self) -> None:
        service = SimpleNamespace(get_profile=AsyncMock(return_value=None))
        menus = SimpleNamespace(send_steam_result=AsyncMock())
        controller = SteamController(service, menus)
        await controller.handle_interaction(
            "group",
            "group-openid",
            "member-openid",
            "steam:profile",
            "interaction-id",
        )
        menus.send_steam_result.assert_awaited_once_with(
            "group",
            "group-openid",
            copy.NOT_BOUND,
            bound=False,
            event_id="interaction-id",
        )


class SteamCardTests(unittest.IsolatedAsyncioTestCase):
    async def test_renderer_outputs_png_with_player_avatar(self) -> None:
        avatar = BytesIO()
        Image.new("RGB", (184, 184), (30, 120, 210)).save(avatar, format="PNG")
        response = httpx.Response(
            200,
            content=avatar.getvalue(),
            request=httpx.Request("GET", "https://avatars.example/player.jpg"),
        )
        http = SimpleNamespace(get=AsyncMock(return_value=response))
        rendered = await SteamCardRenderer(http).render("status", PlayerResult(player()))

        self.assertTrue(rendered.startswith(b"\x89PNG\r\n\x1a\n"))
        with Image.open(BytesIO(rendered)) as card:
            self.assertEqual(card.size, (820, 330))
        http.get.assert_awaited()


if __name__ == "__main__":
    unittest.main()
