from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from main import MessageContext, handle_message
from ui.interactions import handle_interaction
from ui.keyboards import (
    build_action_test_keyboard,
    build_collection_keyboard,
    build_daily_draw_keyboard,
    build_experiments_keyboard,
    build_gift_keyboard,
    build_gift_periods_keyboard,
    build_help_keyboard,
    build_main_keyboard,
    build_notices_keyboard,
    build_services_keyboard,
)
from ui import copywriting as copy
from ui.menus import MenuService, TerminalStatus


class KeyboardTests(unittest.TestCase):
    @staticmethod
    def _button_data(keyboard: object) -> list[str]:
        payload = keyboard.to_dict()
        return [
            button["action"]["data"]
            for row in payload["content"]["rows"]
            for button in row["buttons"]
        ]

    def test_main_keyboard_has_only_four_approved_entries(self) -> None:
        payload = build_main_keyboard().to_dict()
        rows = payload["content"]["rows"]

        self.assertEqual(len(rows), 2)
        self.assertTrue(all(len(row["buttons"]) == 2 for row in rows))
        data = [
            button["action"]["data"]
            for row in rows
            for button in row["buttons"]
        ]
        self.assertEqual(
            data,
            [
                "/市政服务",
                "/实验项目",
                "/公告记录",
                "/使用说明",
            ],
        )
        self.assertTrue(
            all(
                button["action"]["type"] == 2
                and button["action"]["enter"] is True
                for row in rows
                for button in row["buttons"]
            )
        )
        self.assertTrue(
            all(
                "group_id" not in button
                for row in rows
                for button in row["buttons"]
            )
        )

    def test_every_official_menu_omits_undocumented_button_group_id(self) -> None:
        keyboards = (
            build_main_keyboard(),
            build_collection_keyboard(),
            build_daily_draw_keyboard(),
            build_services_keyboard(),
            build_experiments_keyboard(),
            build_notices_keyboard(),
            build_help_keyboard(),
            build_gift_keyboard(),
            build_gift_periods_keyboard(["第十二期"]),
        )
        for keyboard in keyboards:
            rows = keyboard.to_dict()["content"]["rows"]
            self.assertTrue(
                all(
                    "group_id" not in button
                    for row in rows
                    for button in row["buttons"]
                )
            )

    def test_second_level_menus_have_only_actions_and_home(self) -> None:
        self.assertEqual(
            self._button_data(build_services_keyboard()),
            [
                "/礼包查询",
                "/每日单抽",
                "/图鉴",
                "/蜡笔板",
                "/返回终端",
            ],
        )

    def test_gift_buttons_emit_chinese_commands(self) -> None:
        self.assertEqual(
            self._button_data(build_gift_keyboard()),
            ["/礼包排行", "/礼包期次", "/礼包搜索说明", "/市政服务"],
        )
        self.assertEqual(
            self._button_data(build_gift_periods_keyboard(["第十二期", "第十一期"])),
            [
                "/礼包期次 第十二期",
                "/礼包期次 第十一期",
                "/礼包查询",
            ],
        )
        self.assertEqual(
            self._button_data(
                build_gift_periods_keyboard(
                    ["皮拉活动礼包第一周"], page=1, total_pages=2
                )
            ),
            ["/礼包期次 皮拉活动礼包第一周", "/礼包列表 2", "/礼包查询"],
        )

    def test_daily_draw_buttons_emit_chinese_commands(self) -> None:
        self.assertEqual(
            self._button_data(build_daily_draw_keyboard()),
            ["/每日单抽", "/抽取记录", "/市政服务"],
        )
        self.assertEqual(
            self._button_data(build_collection_keyboard()),
            ["/图鉴", "/每日单抽", "/市政服务"],
        )

    def test_non_service_menus_use_stable_data(self) -> None:
        self.assertEqual(
            self._button_data(build_experiments_keyboard()),
            ["/随机实验", "/对话测试", "/返回终端"],
        )
        self.assertEqual(
            self._button_data(build_notices_keyboard()),
            ["/最近更新", "/终端状态", "/返回终端"],
        )
        self.assertEqual(
            self._button_data(build_help_keyboard()),
            ["/基础用法", "/反馈建议", "/返回终端"],
        )

    def test_action_test_keyboard_matches_official_action_types(self) -> None:
        payload = build_action_test_keyboard().to_dict()
        buttons = [
            button
            for row in payload["content"]["rows"]
            for button in row["buttons"]
        ]

        self.assertEqual([button["action"]["type"] for button in buttons], [1, 2, 0, 1])
        self.assertTrue(buttons[1]["action"]["enter"])
        self.assertEqual(buttons[1]["action"]["data"], "/test-markdown")
        self.assertTrue(buttons[2]["action"]["data"].startswith("https://"))
        self.assertTrue(
            all(button["action"]["unsupport_tips"] for button in buttons)
        )


class MenuTests(unittest.IsolatedAsyncioTestCase):
    async def test_long_gift_view_is_split_without_losing_entries(self) -> None:
        messages: list[object] = []

        def build_text(content: str, **_: object) -> object:
            message = SimpleNamespace(content=content)
            messages.append(message)
            return message

        api = SimpleNamespace(
            build_text_body=Mock(side_effect=build_text),
            post_group_message=AsyncMock(return_value={"id": "gift-message"}),
        )
        menus = MenuService(api, TerminalStatus())
        entries = [
            f"**{index}. 完整礼包{index}**\n价格、价值、每元折算水晶叶和推荐等级"
            for index in range(1, 301)
        ]
        content = "# 最新一期\n\n" + "\n\n".join(entries)

        await menus.send_gift_view(
            "group", "group-openid", content, reply_to="incoming-message"
        )

        sent = "\n\n".join(message.content for message in messages)
        for index in range(1, 301):
            self.assertIn(f"完整礼包{index}", sent)
        self.assertGreater(len(messages), 1)

    async def test_message_menu_route_calls_ui_handler(self) -> None:
        show_menu = AsyncMock(return_value={"id": "menu-message"})
        context = MessageContext(
            platform="qq_official",
            scene_type="c2c",
            group_id=None,
            user_id="user-openid",
            message_id="message-menu",
            content="菜单",
            event_type="C2C_MESSAGE_CREATE",
            message_type=0,
            reply=AsyncMock(),
            show_main_menu=show_menu,
        )

        await handle_message(context)

        show_menu.assert_awaited_once_with()
        context.reply.assert_not_awaited()

    async def test_group_menu_sends_markdown_and_keyboard(self) -> None:
        api = SimpleNamespace(
            build_text_body=Mock(return_value="message-body"),
            post_group_message=AsyncMock(return_value={"id": "menu-message"}),
        )
        menus = MenuService(api, TerminalStatus())

        await menus.send_main_menu("group", "group-openid", "incoming-message")

        api.build_text_body.assert_called_once_with(
            copy.HOME_MARKDOWN,
            reply_to="incoming-message",
            markdown=True,
        )
        args, kwargs = api.post_group_message.await_args
        self.assertEqual(args, ("group-openid", "message-body"))
        self.assertIn("keyboard", kwargs)

    async def test_command_button_route_uses_inbound_message_id(self) -> None:
        message = Mock()
        api = SimpleNamespace(
            build_text_body=Mock(return_value=message),
            post_group_message=AsyncMock(return_value={"id": "services-menu"}),
        )
        menus = MenuService(api, TerminalStatus())
        context = SimpleNamespace(
            content="/市政服务",
            scene_type="group",
            group_id="group-openid",
            user_id="member-openid",
            message_id="button-command-message-id",
            reply=AsyncMock(),
        )

        self.assertTrue(await menus.handle_text(context))

        api.build_text_body.assert_called_once_with(
            copy.SERVICES_MARKDOWN,
            reply_to="button-command-message-id",
            markdown=True,
        )

    async def test_chinese_help_alias_reuses_help_menu(self) -> None:
        message = Mock()
        api = SimpleNamespace(
            build_text_body=Mock(return_value=message),
            post_group_message=AsyncMock(return_value={"id": "help-menu"}),
        )
        menus = MenuService(api, TerminalStatus())
        context = SimpleNamespace(
            content="/帮助",
            scene_type="group",
            group_id="group-openid",
            user_id="member-openid",
            message_id="help-command-message-id",
            reply=AsyncMock(),
        )

        self.assertTrue(await menus.handle_text(context))

        api.build_text_body.assert_called_once_with(
            copy.HELP_MARKDOWN,
            reply_to="help-command-message-id",
            markdown=True,
        )

    async def test_bare_help_panel_command_reuses_help_menu(self) -> None:
        message = Mock()
        api = SimpleNamespace(
            build_text_body=Mock(return_value=message),
            post_group_message=AsyncMock(return_value={"id": "help-menu"}),
        )
        menus = MenuService(api, TerminalStatus())
        context = SimpleNamespace(
            content="帮助",
            scene_type="group",
            group_id="group-openid",
            user_id="member-openid",
            message_id="help-command-message-id",
            reply=AsyncMock(),
        )

        self.assertTrue(await menus.handle_text(context))

        api.build_text_body.assert_called_once_with(
            copy.HELP_MARKDOWN,
            reply_to="help-command-message-id",
            markdown=True,
        )

    async def test_group_image_upload_is_followed_by_passive_media_reply(self) -> None:
        api = SimpleNamespace(
            upload_group_file=AsyncMock(return_value={"file_info": "media-token"}),
            post_group_message=AsyncMock(return_value={"id": "image-message"}),
            next_msg_seq=Mock(return_value=42),
        )
        menus = MenuService(api, TerminalStatus())

        await menus.send_image(
            "group",
            "group-openid",
            b"png-bytes",
            reply_to="incoming-message-id",
        )

        upload = api.upload_group_file.await_args.args[1].to_dict()
        self.assertEqual(upload["file_type"], 1)
        self.assertTrue(upload["file_data"])
        message = api.post_group_message.await_args.args[1].to_dict()
        self.assertEqual(message["msg_type"], 7)
        self.assertEqual(message["msg_id"], "incoming-message-id")
        self.assertEqual(message["media"]["file_info"], "media-token")


class InteractionTests(unittest.IsolatedAsyncioTestCase):
    async def test_callback_is_acked_then_dispatches_services_menu(self) -> None:
        order: list[str] = []

        async def ack(interaction_id: str) -> None:
            self.assertEqual(interaction_id, "interaction-1")
            order.append("ack")

        async def services(
            scene: str, chat_id: str, *, event_id: str | None = None
        ) -> dict[str, str]:
            self.assertEqual((scene, chat_id), ("group", "group-openid"))
            self.assertIsNone(event_id)
            order.append("action")
            return {"id": "daily-menu"}

        api = SimpleNamespace(acknowledge_interaction=ack)
        menus = SimpleNamespace(
            send_services_menu=services,
            send_experiments_menu=AsyncMock(),
            send_notices_menu=AsyncMock(),
            send_help_menu=AsyncMock(),
            send_main_menu=AsyncMock(),
            send_action_test_menu=AsyncMock(),
            send_terminal_status=AsyncMock(),
            send_plain_text=AsyncMock(),
        )
        raw = {
            "id": "interaction-1",
            "type": 11,
            "chat_type": 1,
            "group_openid": "group-openid",
            "group_member_openid": "member-openid",
            "data": {
                "type": 11,
                "resolved": {
                    "button_data": "menu:services",
                    "button_id": "home_services",
                },
            },
        }

        await handle_interaction("INTERACTION_CREATE", raw, api, menus)

        self.assertEqual(order, ["ack", "action"])

    async def test_interaction_menu_body_contains_event_id(self) -> None:
        message = Mock()
        message.to_dict.return_value = {
            "msg_type": 2,
            "markdown": {"content": "services"},
        }
        api = SimpleNamespace(
            build_text_body=Mock(return_value=message),
            post_group_message=AsyncMock(return_value={"id": "menu-message"}),
        )
        menus = MenuService(api, TerminalStatus())

        await menus.send_services_menu(
            "group", "group-openid", event_id="interaction-event-id"
        )

        outbound = api.post_group_message.await_args.args[1]
        self.assertEqual(outbound.to_dict()["event_id"], "interaction-event-id")
        self.assertNotIn("msg_id", outbound.to_dict())


if __name__ == "__main__":
    unittest.main()
