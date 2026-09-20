from __future__ import annotations

import os
import logging
import unittest
from unittest.mock import AsyncMock, patch

from config import ConfigurationError, load_settings
from main import (
    MessageContext,
    REPLY_TEXT,
    SecretRedactionFilter,
    handle_message,
    make_message_context,
)


class MessageHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_ping_replies(self) -> None:
        reply = AsyncMock(return_value={"id": "reply-1"})
        context = MessageContext(
            platform="qq_official",
            scene_type="group",
            group_id="group-openid",
            user_id="member-openid",
            message_id="message-1",
            content=" ping ",
            event_type="GROUP_AT_MESSAGE_CREATE",
            message_type=0,
            reply=reply,
        )

        await handle_message(context)

        reply.assert_awaited_once_with(REPLY_TEXT)

    async def test_unmatched_message_does_not_reply(self) -> None:
        reply = AsyncMock()
        context = MessageContext(
            platform="qq_official",
            scene_type="c2c",
            group_id=None,
            user_id="user-openid",
            message_id="message-2",
            content="hello",
            event_type="C2C_MESSAGE_CREATE",
            message_type=0,
            reply=reply,
        )

        await handle_message(context)

        reply.assert_not_awaited()

    async def test_chinese_slash_menu_uses_existing_main_menu_handler(self) -> None:
        show_menu = AsyncMock(return_value={"id": "menu"})
        context = MessageContext(
            platform="qq_official",
            scene_type="group",
            group_id="group-openid",
            user_id="member-openid",
            message_id="message-menu",
            content="/菜单",
            event_type="GROUP_AT_MESSAGE_CREATE",
            message_type=0,
            reply=AsyncMock(),
            show_main_menu=show_menu,
        )

        await handle_message(context)

        show_menu.assert_awaited_once_with()

    async def test_unmatched_plugin_falls_through_to_menu_handler(self) -> None:
        gift_handler = AsyncMock(return_value=False)
        draw_handler = AsyncMock(return_value=False)
        menu_handler = AsyncMock(return_value=True)
        context = MessageContext(
            platform="qq_official",
            scene_type="group",
            group_id="group-openid",
            user_id="member-openid",
            message_id="button-command-message-id",
            content="/市政服务",
            event_type="GROUP_AT_MESSAGE_CREATE",
            message_type=0,
            reply=AsyncMock(),
            gift_handler=gift_handler,
            draw_handler=draw_handler,
            menu_handler=menu_handler,
        )

        await handle_message(context)

        gift_handler.assert_awaited_once_with(context)
        draw_handler.assert_awaited_once_with(context)
        menu_handler.assert_awaited_once_with(context)


class ConfigurationTests(unittest.TestCase):
    def test_missing_credentials_has_clear_error(self) -> None:
        with patch.dict(os.environ, {"QQ_APP_ID": "", "QQ_APP_SECRET": ""}):
            with self.assertRaisesRegex(ConfigurationError, "QQ_APP_ID.*QQ_APP_SECRET"):
                load_settings()


class AdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_group_event_uses_openids_and_passive_reply(self) -> None:
        from qqbot_agent_sdk import EventParser

        event = EventParser().parse(
            "GROUP_AT_MESSAGE_CREATE",
            {
                "id": "message-3",
                "group_openid": "group-openid",
                "author": {"member_openid": "member-openid"},
                "content": " ping ",
                "timestamp": "2026-09-11T12:00:00+08:00",
            },
        )
        self.assertIsNotNone(event)
        send_text = AsyncMock(return_value={"id": "reply-3"})

        context = make_message_context(event, "GROUP_AT_MESSAGE_CREATE", send_text)
        await handle_message(context)

        self.assertEqual(context.scene_type, "group")
        self.assertEqual(context.group_id, "group-openid")
        self.assertEqual(context.user_id, "member-openid")
        send_text.assert_awaited_once_with(
            "group",
            "group-openid",
            REPLY_TEXT,
            reply_to="message-3",
            markdown=False,
        )

    async def test_sdk_group_intent_matches_official_bit(self) -> None:
        from qqbot_agent_sdk import Intent

        self.assertEqual(int(Intent.GROUP_MESSAGES), 1 << 25)


class LoggingTests(unittest.TestCase):
    def test_secret_and_access_token_are_redacted(self) -> None:
        record = logging.LogRecord(
            "test",
            logging.INFO,
            __file__,
            1,
            "secret=%s Authorization: QQBot abc-token access_token=xyz-token",
            ("real-secret",),
            None,
        )
        SecretRedactionFilter(("real-secret",)).filter(record)
        rendered = record.getMessage()

        self.assertNotIn("real-secret", rendered)
        self.assertNotIn("abc-token", rendered)
        self.assertNotIn("xyz-token", rendered)


if __name__ == "__main__":
    unittest.main()
