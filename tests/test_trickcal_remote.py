from __future__ import annotations

import logging
import os
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

import httpx

from config import load_settings
from trickcal import copywriting as copy
from trickcal.client import (
    TrickcalAuthError,
    TrickcalClient,
    TrickcalInvalidResponseError,
    TrickcalProfileNotFoundError,
    TrickcalRateLimitError,
    TrickcalTimeoutError,
    TrickcalUnavailableError,
)
from trickcal.commands import TrickcalController
from trickcal.card import TrickcalProgressCardRenderer
from trickcal.formatter import TrickcalFormatter
from trickcal.models import TrickcalAttributeStat, TrickcalIdentity, TrickcalSummary
from trickcal.remote_service import TrickcalRemoteService
from ui.keyboards import build_trickcal_keyboard


def identity(scene: str = "group") -> TrickcalIdentity:
    return TrickcalIdentity("qq_official", "member-openid", scene)


class RemoteClientTests(unittest.IsolatedAsyncioTestCase):
    async def _client(self, handler: Any) -> TrickcalClient:
        self.http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        self.addAsyncCleanup(self.http.aclose)
        return TrickcalClient(
            self.http,
            api_base_url="https://gift.example.com",
            bot_api_key="secret-not-for-logs",
        )

    async def test_login_ticket_sends_authenticated_unmodified_identity(self) -> None:
        received: dict[str, Any] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            received["path"] = request.url.path
            received["authorization"] = request.headers["authorization"]
            received["body"] = request.json() if hasattr(request, "json") else None
            return httpx.Response(200, json={"url": "https://gift.example.com/tr-board/entry?t=private"})

        # httpx Request deliberately has no json() helper; decode in the test
        # transport so the client remains the only production response parser.
        def json_handler(request: httpx.Request) -> httpx.Response:
            import json

            received["path"] = request.url.path
            received["authorization"] = request.headers["authorization"]
            received["body"] = json.loads(request.content)
            return httpx.Response(200, json={"url": "https://gift.example.com/tr-board/entry?t=private"})

        client = await self._client(json_handler)
        ticket = await client.create_login_ticket(identity("group"))

        self.assertEqual(ticket.url, "https://gift.example.com/tr-board/entry?t=private")
        self.assertEqual(received["path"], "/api/bot/tr-board/login-ticket")
        self.assertEqual(received["authorization"], "Bearer secret-not-for-logs")
        self.assertEqual(received["body"], {"platform": "qq_official", "user_id": "member-openid", "scene_type": "group"})

    async def test_login_ticket_accepts_wrapped_contract(self) -> None:
        client = await self._client(
            lambda request: httpx.Response(200, json={"ok": True, "data": {"url": "https://gift.example.com/tr-board/entry?t=private"}})
        )
        self.assertTrue((await client.create_login_ticket(identity())).url.startswith("https://gift.example.com/"))

    async def test_login_ticket_accepts_deployed_ok_root_contract(self) -> None:
        client = await self._client(
            lambda request: httpx.Response(200, json={"ok": True, "url": "https://gift.example.com/tr-board/entry?t=private"})
        )
        self.assertTrue((await client.create_login_ticket(identity())).url.startswith("https://gift.example.com/"))

    async def test_login_ticket_rejects_untrusted_url(self) -> None:
        client = await self._client(
            lambda request: httpx.Response(200, json={"url": "https://evil.example/tr-board/entry?t=private"})
        )
        with self.assertRaises(TrickcalInvalidResponseError):
            await client.create_login_ticket(identity())

    async def test_login_ticket_is_not_retried_after_temporary_failure(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(503, json={"error": "internal_error"})

        client = await self._client(handler)
        with self.assertRaises(TrickcalUnavailableError):
            await client.create_login_ticket(identity())
        self.assertEqual(calls, 1)

    async def test_summary_retries_one_temporary_failure(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            if calls == 1:
                return httpx.Response(503)
            return httpx.Response(200, json={"profile_exists": True, "owned_characters": 46})

        client = await self._client(handler)
        summary = await client.get_summary(identity("c2c"))
        self.assertEqual(calls, 2)
        self.assertTrue(summary.profile_exists)
        self.assertEqual(summary.owned_characters, 46)

    async def test_summary_accepts_deployed_ok_root_contract(self) -> None:
        client = await self._client(
            lambda request: httpx.Response(200, json={"ok": True, "profile_exists": False})
        )
        self.assertFalse((await client.get_summary(identity())).profile_exists)

    async def test_summary_parses_attribute_statistics_and_crayons(self) -> None:
        client = await self._client(
            lambda request: httpx.Response(
                200,
                json={
                    "ok": True,
                    "profile_exists": True,
                    "gold_crayons_required": 76,
                    "gold_crayons_used": 12,
                    "attribute_stats": [
                        {
                            "key": "attack",
                            "label": "攻击力",
                            "lit_nodes": 4,
                            "total_nodes": 144,
                            "bonus_percent": 12,
                        }
                    ],
                },
            )
        )
        summary = await client.get_summary(identity())
        self.assertEqual(summary.gold_crayons_required, 76)
        self.assertEqual(summary.gold_crayons_used, 12)
        self.assertEqual(summary.attribute_stats[0].label, "攻击力")
        self.assertEqual(summary.attribute_stats[0].bonus_percent, 12)

    async def test_api_errors_are_typed(self) -> None:
        cases = [
            (401, {}, TrickcalAuthError),
            (429, {}, TrickcalRateLimitError),
            (200, {"ok": False, "error": "profile_not_found"}, TrickcalProfileNotFoundError),
            (500, {}, TrickcalUnavailableError),
        ]
        for status, payload, expected in cases:
            client = await self._client(lambda request, s=status, p=payload: httpx.Response(s, json=p))
            with self.subTest(status=status), self.assertRaises(expected):
                await client.get_summary(identity())

    async def test_timeout_and_invalid_json_are_typed(self) -> None:
        def timeout_handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("slow", request=request)

        client = await self._client(timeout_handler)
        with self.assertRaises(TrickcalTimeoutError):
            await client.create_login_ticket(identity())

        client = await self._client(lambda request: httpx.Response(200, content=b"not json"))
        with self.assertRaises(TrickcalInvalidResponseError):
            await client.get_summary(identity())

    async def test_client_logs_do_not_contain_identity_key_or_ticket(self) -> None:
        client = await self._client(
            lambda request: httpx.Response(200, json={"url": "https://gift.example.com/tr-board/entry?t=private-ticket"})
        )
        with self.assertLogs("elena.qq.trickcal.client", logging.INFO) as captured:
            await client.create_login_ticket(identity())
        rendered = "\n".join(captured.output)
        self.assertNotIn("member-openid", rendered)
        self.assertNotIn("secret-not-for-logs", rendered)
        self.assertNotIn("private-ticket", rendered)

    async def test_health_check_calls_website_status_endpoint(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.method, "GET")
            self.assertEqual(request.url.path, "/api/bot/tr-board/status")
            self.assertEqual(request.headers["authorization"], "Bearer secret-not-for-logs")
            return httpx.Response(200, json={"ok": True})

        client = await self._client(handler)
        self.assertTrue(await client.health_check())


class RemoteFormatterTests(unittest.TestCase):
    def test_formatter_displays_only_fields_returned_by_website(self) -> None:
        text = TrickcalFormatter.summary(TrickcalSummary(profile_exists=True, owned_characters=46, total_characters=63, gold_required=1_280_000))
        self.assertIn("已登记角色：46 / 63", text)
        self.assertNotIn("金币", text)
        self.assertNotIn("已完成节点", text)
        self.assertNotIn("金蜡笔：0", text)

    def test_formatter_keeps_only_remaining_gold_crayons(self) -> None:
        text = TrickcalFormatter.summary(
            TrickcalSummary(gold_required=1_280_000, gold_crayons_required=76)
        )
        self.assertIn("预计还需金蜡笔：76", text)
        self.assertNotIn("金币", text)

    def test_progress_card_renders_attribute_statistics(self) -> None:
        stats = tuple(
            TrickcalAttributeStat(key, label, index, 100 + index, index * 3)
            for index, (key, label) in enumerate(
                (("attack", "攻击力"), ("critical", "暴击"), ("health", "生命值"), ("defense", "防御力"), ("critical_resistance", "暴击抗性")),
                start=1,
            )
        )
        renderer = TrickcalProgressCardRenderer(
            Path(__file__).resolve().parents[1] / "trickcal_assets" / "attribute-icons.png"
        )
        self.assertEqual(len(renderer._load_icons()), 5)
        self.assertIsNotNone(renderer._icon(0))
        rendered = renderer.render(
            TrickcalSummary(
                completed_nodes=18,
                total_nodes=702,
                gold_crayons_used=12,
                gold_crayons_required=76,
                attribute_stats=stats,
            )
        )
        from PIL import Image
        import io

        with Image.open(io.BytesIO(rendered)) as image:
            self.assertEqual(image.size, (960, 940))
            self.assertEqual(image.format, "PNG")


class Menus:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    async def send_trickcal_home(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append(("home", args, kwargs))

    async def send_trickcal_login(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append(("login", args, kwargs))

    async def send_trickcal_empty(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append(("empty", args, kwargs))

    async def send_image(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append(("image", args, kwargs))

    async def send_services_menu(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append(("services", args, kwargs))

    async def send_plain_text(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append(("text", args, kwargs))


class RemoteControllerTests(unittest.IsolatedAsyncioTestCase):
    async def test_command_button_open_uses_passive_message_reply(self) -> None:
        class Service:
            async def create_login_ticket(self, value: TrickcalIdentity):
                from trickcal.models import LoginTicketResponse

                self.identity = value
                return LoginTicketResponse("https://gift.example.com/tr-board/entry?t=private")

        class Context:
            scene_type = "group"
            group_id = "group-openid"
            user_id = "member-openid"
            message_id = "message-id"
            content = "/打开蜡笔板"

            async def reply(self, content: str) -> None:
                raise AssertionError(f"unexpected plain reply: {content}")

        menus = Menus(); service = Service()
        handled = await TrickcalController(service, menus, mode="remote").handle_text(Context())
        self.assertTrue(handled)
        self.assertEqual(menus.calls[0][0], "login")
        self.assertEqual(menus.calls[0][1][2], f"<@member-openid>\n{copy.FIRST_ENTRY}")
        self.assertEqual(menus.calls[0][2]["reply_to"], "message-id")
        self.assertEqual(service.identity.user_id, "member-openid")

    def test_trickcal_buttons_emit_chinese_passive_commands(self) -> None:
        buttons = build_trickcal_keyboard().to_dict()["content"]["rows"]
        actions = [item["buttons"][0]["action"] for item in buttons]
        self.assertEqual([item["type"] for item in actions], [2, 2, 2])
        self.assertEqual([item["data"] for item in actions], ["/打开蜡笔板", "/蜡笔板进度", "/市政服务"])
    async def test_disabled_module_keeps_menu_but_reports_unavailable_on_open(self) -> None:
        menus = Menus()
        controller = TrickcalController(None, menus, mode="disabled")
        await controller.handle_interaction("group", "group-openid", "member-openid", "trickcal:open", "event")
        self.assertEqual(menus.calls[0][0], "text")
        self.assertEqual(menus.calls[0][1][2], f"<@member-openid>\n{copy.UNAVAILABLE}")

    async def test_remote_profile_absent_uses_open_and_back_view(self) -> None:
        class Service:
            async def get_summary(self, value: TrickcalIdentity) -> TrickcalSummary:
                self.identity = value
                return TrickcalSummary(profile_exists=False)

        menus = Menus(); service = Service()
        controller = TrickcalController(service, menus, mode="remote")
        await controller.handle_interaction("group", "group-openid", "member-openid", "trickcal:progress", "event")
        self.assertEqual(menus.calls[0][0], "empty")
        self.assertEqual(menus.calls[0][2]["content"], f"<@member-openid>\n{copy.EMPTY}")
        self.assertEqual(service.identity.scene_type, "group")
        self.assertEqual(service.identity.user_id, "member-openid")

    async def test_text_progress_sends_attribute_card_then_addressed_menu(self) -> None:
        stats = tuple(
            TrickcalAttributeStat(key, label, 1, 10, 2)
            for key, label in (
                ("attack", "攻击力"),
                ("critical", "暴击"),
                ("health", "生命值"),
                ("defense", "防御力"),
                ("critical_resistance", "暴击抗性"),
            )
        )

        class Service:
            async def get_summary(self, value: TrickcalIdentity) -> TrickcalSummary:
                return TrickcalSummary(
                    profile_exists=True,
                    completed_nodes=5,
                    total_nodes=50,
                    attribute_stats=stats,
                )

        class Context:
            scene_type = "group"
            group_id = "group-openid"
            user_id = "member-openid"
            message_id = "message-id"
            content = "/蜡笔板进度"

            async def reply(self, content: str) -> None:
                raise AssertionError(f"unexpected plain reply: {content}")

        menus = Menus()
        renderer = Mock(render=Mock(return_value=b"card-png"))
        handled = await TrickcalController(
            Service(), menus, mode="remote", progress_card_renderer=renderer
        ).handle_text(Context())

        self.assertTrue(handled)
        self.assertEqual([call[0] for call in menus.calls], ["image", "home"])
        self.assertEqual(menus.calls[0][1][2], b"card-png")
        self.assertEqual(menus.calls[0][2]["reply_to"], "message-id")
        self.assertEqual(menus.calls[1][2]["content"], f"<@member-openid>\n{copy.PROGRESS_CARD_READY}")

    async def test_remote_open_uses_service_ticket_and_c2c_identity(self) -> None:
        class Service:
            async def create_login_ticket(self, value: TrickcalIdentity):
                from trickcal.models import LoginTicketResponse

                self.identity = value
                return LoginTicketResponse("https://gift.example.com/tr-board/entry?t=private")

        menus = Menus(); service = Service()
        controller = TrickcalController(service, menus, mode="remote")
        await controller.handle_interaction("c2c", "openid", "openid", "trickcal:open", "event")
        self.assertEqual(menus.calls[0][0], "login")
        self.assertEqual(menus.calls[0][1][2], copy.FIRST_ENTRY)
        self.assertEqual(service.identity.scene_type, "c2c")

    async def test_open_is_debounced_per_user(self) -> None:
        class Service:
            async def create_login_ticket(self, value: TrickcalIdentity):
                from trickcal.models import LoginTicketResponse

                return LoginTicketResponse("https://gift.example.com/tr-board/entry?t=private")

        menus = Menus(); controller = TrickcalController(Service(), menus, mode="remote")
        await controller.handle_interaction("group", "group", "user", "trickcal:open", "first")
        await controller.handle_interaction("group", "group", "user", "trickcal:open", "second")
        self.assertEqual([call[0] for call in menus.calls], ["login", "text"])


class RemoteConfigurationTests(unittest.TestCase):
    def test_remote_is_default_and_missing_api_values_do_not_raise(self) -> None:
        values = {
            "QQ_APP_ID": "app",
            "QQ_APP_SECRET": "secret",
            "TRICKCAL_MODE": "remote",
            "TRICKCAL_API_BASE_URL": "",
            "TRICKCAL_BOT_API_KEY": "",
        }
        with patch.dict(os.environ, values, clear=True):
            settings = load_settings()
        self.assertEqual(settings.trickcal_mode, "remote")
        self.assertFalse(settings.trickcal_remote_configured)

    def test_unknown_mode_is_safely_disabled(self) -> None:
        with patch.dict(os.environ, {"QQ_APP_ID": "app", "QQ_APP_SECRET": "secret", "TRICKCAL_MODE": "wrong"}, clear=True):
            settings = load_settings()
        self.assertEqual(settings.trickcal_mode, "disabled")
