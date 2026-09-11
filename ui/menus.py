from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any

from . import copywriting as copy
from .keyboards import (
    build_action_test_keyboard,
    build_experiments_keyboard,
    build_help_keyboard,
    build_gift_keyboard,
    build_gift_periods_keyboard,
    build_main_keyboard,
    build_notices_keyboard,
    build_services_keyboard,
    build_steam_keyboard,
    build_steam_result_keyboard,
    build_steam_unbound_keyboard,
)
from steam import copywriting as steam_copy
from gifts.models import GiftPeriod


class TerminalStatus:
    """Minimal thread-safe runtime state; not a monitoring subsystem."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._gateway_online = False

    def set_gateway_online(self, online: bool) -> None:
        with self._lock:
            self._gateway_online = online

    def is_gateway_online(self) -> bool:
        with self._lock:
            return self._gateway_online


@dataclass(slots=True)
class EventReplyMessage:
    """Add the official event_id field missing from SDK 1.2.2's DTO."""

    message: Any
    event_id: str

    def to_dict(self) -> dict[str, Any]:
        payload = self.message.to_dict()
        payload["event_id"] = self.event_id
        return payload


class MenuService:
    def __init__(self, api: Any, status: TerminalStatus) -> None:
        self._api = api
        self._status = status

    async def handle_text(self, context: Any) -> bool:
        """Route commands emitted by type=2 buttons through passive replies."""
        command = context.content.strip().casefold()
        chat_id = context.group_id or context.user_id
        menu_actions = {
            "/返回终端": self.send_main_menu,
            "/市政服务": self.send_services_menu,
            "/实验项目": self.send_experiments_menu,
            "/公告记录": self.send_notices_menu,
            "/使用说明": self.send_help_menu,
            "/steam监测站": self.send_steam_home,
        }
        menu_action = menu_actions.get(command)
        if menu_action is not None:
            await menu_action(context.scene_type, chat_id, context.message_id)
            return True

        text_actions = {
            "/每日抽取": copy.DAILY_DRAW_PLACEHOLDER,
            "/图鉴": copy.COLLECTION_PLACEHOLDER,
            "/随机实验": copy.RANDOM_EXPERIMENT_PLACEHOLDER,
            "/对话测试": copy.CHAT_EXPERIMENT_PLACEHOLDER,
            "/最近更新": copy.RECENT_UPDATES,
            "/终端状态": copy.terminal_status_text(
                self._status.is_gateway_online()
            ),
            "/基础用法": copy.BASIC_HELP,
            "/反馈建议": copy.FEEDBACK_PLACEHOLDER,
        }
        content = text_actions.get(command)
        if content is None:
            return False
        await context.reply(content)
        return True

    async def _send_markdown_keyboard(
        self,
        scene: str,
        chat_id: str,
        content: str,
        keyboard: Any,
        *,
        reply_to: str | None = None,
        event_id: str | None = None,
    ) -> dict[str, Any]:
        message = self._api.build_text_body(
            content,
            reply_to=reply_to,
            markdown=True,
        )
        outbound = EventReplyMessage(message, event_id) if event_id else message
        if scene == "c2c":
            return await self._api.post_c2c_message(
                chat_id, outbound, keyboard=keyboard
            )
        if scene == "group":
            return await self._api.post_group_message(
                chat_id, outbound, keyboard=keyboard
            )
        raise ValueError(f"市政终端暂不支持场景：{scene}")

    async def send_main_menu(
        self,
        scene: str,
        chat_id: str,
        reply_to: str | None = None,
        *,
        event_id: str | None = None,
    ) -> dict[str, Any]:
        return await self._send_markdown_keyboard(
            scene,
            chat_id,
            copy.HOME_MARKDOWN,
            build_main_keyboard(),
            reply_to=reply_to,
            event_id=event_id,
        )

    async def send_services_menu(
        self,
        scene: str,
        chat_id: str,
        reply_to: str | None = None,
        *,
        event_id: str | None = None,
    ) -> dict[str, Any]:
        return await self._send_markdown_keyboard(
            scene,
            chat_id,
            copy.SERVICES_MARKDOWN,
            build_services_keyboard(),
            reply_to=reply_to,
            event_id=event_id,
        )

    async def send_steam_home(
        self,
        scene: str,
        chat_id: str,
        reply_to: str | None = None,
        *,
        event_id: str | None = None,
    ) -> dict[str, Any]:
        return await self._send_markdown_keyboard(
            scene,
            chat_id,
            steam_copy.STEAM_HOME,
            build_steam_keyboard(),
            reply_to=reply_to,
            event_id=event_id,
        )

    async def send_steam_result(
        self,
        scene: str,
        chat_id: str,
        content: str,
        *,
        bound: bool = True,
        event_id: str | None = None,
    ) -> dict[str, Any]:
        return await self._send_markdown_keyboard(
            scene,
            chat_id,
            content,
            build_steam_result_keyboard() if bound else build_steam_unbound_keyboard(),
            event_id=event_id,
        )

    async def send_gift_view(
        self,
        scene: str,
        chat_id: str,
        content: str,
        *,
        periods: tuple[GiftPeriod, ...] = (),
        period_page: int = 1,
        period_total_pages: int = 1,
        reply_to: str | None = None,
    ) -> dict[str, Any]:
        keyboard = (
            build_gift_periods_keyboard(
                [period.name for period in periods],
                page=period_page,
                total_pages=period_total_pages,
            )
            if periods
            else build_gift_keyboard()
        )
        return await self._send_markdown_keyboard(
            scene,
            chat_id,
            content,
            keyboard,
            reply_to=reply_to,
        )

    async def send_experiments_menu(
        self,
        scene: str,
        chat_id: str,
        reply_to: str | None = None,
        *,
        event_id: str | None = None,
    ) -> dict[str, Any]:
        return await self._send_markdown_keyboard(
            scene,
            chat_id,
            copy.EXPERIMENTS_MARKDOWN,
            build_experiments_keyboard(),
            reply_to=reply_to,
            event_id=event_id,
        )

    async def send_notices_menu(
        self,
        scene: str,
        chat_id: str,
        reply_to: str | None = None,
        *,
        event_id: str | None = None,
    ) -> dict[str, Any]:
        return await self._send_markdown_keyboard(
            scene,
            chat_id,
            copy.NOTICES_MARKDOWN,
            build_notices_keyboard(),
            reply_to=reply_to,
            event_id=event_id,
        )

    async def send_help_menu(
        self,
        scene: str,
        chat_id: str,
        reply_to: str | None = None,
        *,
        event_id: str | None = None,
    ) -> dict[str, Any]:
        return await self._send_markdown_keyboard(
            scene,
            chat_id,
            copy.HELP_MARKDOWN,
            build_help_keyboard(),
            reply_to=reply_to,
            event_id=event_id,
        )

    async def send_action_test_menu(
        self,
        scene: str,
        chat_id: str,
        reply_to: str | None = None,
        *,
        event_id: str | None = None,
    ) -> dict[str, Any]:
        """Hidden test page retained for development; absent from normal menus."""
        return await self._send_markdown_keyboard(
            scene,
            chat_id,
            "# 隐藏功能测试\n\n这个页面不在普通市政终端入口中。",
            build_action_test_keyboard(),
            reply_to=reply_to,
            event_id=event_id,
        )

    async def send_terminal_status(
        self, scene: str, chat_id: str, *, event_id: str | None = None
    ) -> dict[str, Any]:
        return await self.send_plain_text(
            scene,
            chat_id,
            copy.terminal_status_text(self._status.is_gateway_online()),
            event_id=event_id,
        )

    async def send_plain_text(
        self,
        scene: str,
        chat_id: str,
        content: str,
        *,
        event_id: str | None = None,
    ) -> dict[str, Any]:
        if not event_id:
            return await self._api.send_text(scene, chat_id, content, markdown=False)
        message = self._api.build_text_body(content, markdown=False)
        outbound = EventReplyMessage(message, event_id)
        if scene == "c2c":
            return await self._api.post_c2c_message(chat_id, outbound)
        if scene == "group":
            return await self._api.post_group_message(chat_id, outbound)
        raise ValueError(f"市政终端暂不支持场景：{scene}")
