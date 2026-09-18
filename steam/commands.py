from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable
from typing import Any

from . import copywriting as copy
from .models import OfficialIdentity
from .service import SteamService
from .service import PlayerResult


logger = logging.getLogger("elena.qq.steam")


def parse_steam_command(content: str) -> tuple[str, str] | None:
    text = content.strip()
    lowered = text.casefold()
    if lowered in {"steam", "/steam"}:
        return "home", ""
    if lowered in {
        "steam状态", "steam 状态", "/steam status", "当前steam", "steamstatus", "/当前状态"
    }:
        return "status", ""
    if lowered in {
        "我的steam", "steam档案", "steam 档案", "/steam profile", "/我的档案"
    }:
        return "profile", ""
    matched = re.fullmatch(r"(?:绑定steam|steam绑定)\s+(.+)", text, re.I)
    if matched:
        return "bind", matched.group(1).strip()
    if lowered in {"绑定steam", "steam绑定", "/身份登记"}:
        return "bind_guide", ""
    if lowered in {"解绑steam", "steam解绑", "/steam unbind", "/解除登记"}:
        return "unbind", ""
    return None


class SteamController:
    def __init__(
        self,
        service: SteamService,
        menus: Any,
        card_renderer: Callable[[str, PlayerResult], Awaitable[bytes]] | None = None,
    ) -> None:
        self._service = service
        self._menus = menus
        self._card_renderer = card_renderer

    @staticmethod
    def _identity(scene: str, user_id: str, chat_id: str) -> OfficialIdentity:
        return OfficialIdentity(
            platform="qq_official",
            user_id=user_id,
            group_id=chat_id if scene == "group" else "",
        )

    async def handle_text(self, context: Any) -> bool:
        parsed = parse_steam_command(context.content)
        if parsed is None:
            return False
        action, argument = parsed
        chat_id = context.group_id or context.user_id
        identity = self._identity(context.scene_type, context.user_id, chat_id)
        if action == "home":
            await self._menus.send_steam_home(
                context.scene_type, chat_id, context.message_id
            )
            return True
        if action in {"profile", "status"} and self._card_renderer is not None:
            await self._send_player_card(action, context, identity, chat_id)
            return True
        content = await self._execute(action, argument, identity)
        await context.reply(content)
        return True

    async def _send_player_card(
        self, action: str, context: Any, identity: OfficialIdentity, chat_id: str
    ) -> None:
        try:
            result = await self._service.get_profile(identity)
        except Exception as exc:
            logger.exception(
                "[STEAM] status query failed | action=%s | scene=%s",
                action,
                context.scene_type,
            )
            await context.reply(copy.error_text(exc))
            return
        if result is None:
            await context.reply(copy.NOT_BOUND)
            return
        try:
            image = await self._card_renderer(action, result)
            await self._menus.send_image(
                context.scene_type,
                chat_id,
                image,
                reply_to=context.message_id,
                file_name=f"steam-{action}.png",
            )
            logger.info(
                "[STEAM] status card sent | action=%s | scene=%s | steam_id=%s",
                action,
                context.scene_type,
                result.player.steam_id,
            )
        except Exception:
            logger.exception(
                "[STEAM] status card failed; falling back to text | action=%s | scene=%s",
                action,
                context.scene_type,
            )
            content = copy.profile(result) if action == "profile" else copy.status(result)
            await context.reply(content)

    async def handle_interaction(
        self,
        scene: str,
        chat_id: str,
        user_id: str,
        button_data: str,
        event_id: str | None,
    ) -> None:
        identity = self._identity(scene, user_id, chat_id)
        if button_data == "steam:home":
            await self._menus.send_steam_home(scene, chat_id, event_id=event_id)
            return
        if button_data == "steam:back":
            await self._menus.send_services_menu(scene, chat_id, event_id=event_id)
            return
        action = button_data.removeprefix("steam:")
        if action in {"profile", "status"}:
            try:
                result = await self._service.get_profile(identity)
                if result is None:
                    await self._menus.send_steam_result(
                        scene, chat_id, copy.NOT_BOUND, bound=False, event_id=event_id
                    )
                else:
                    content = copy.profile(result) if action == "profile" else copy.status(result)
                    await self._menus.send_steam_result(
                        scene, chat_id, content, bound=True, event_id=event_id
                    )
            except Exception as exc:
                logger.exception(
                    "[STEAM] interaction query failed | action=%s | scene_group=%s | user_id=%s",
                    action, bool(identity.group_id), identity.user_id,
                )
                await self._menus.send_plain_text(
                    scene, chat_id, copy.error_text(exc), event_id=event_id
                )
        else:
            content = await self._execute(action, "", identity)
            await self._menus.send_plain_text(
                scene, chat_id, content, event_id=event_id
            )

    async def _execute(
        self, action: str, argument: str, identity: OfficialIdentity
    ) -> str:
        if action in {"bind", "bind_guide"} and not argument:
            return copy.BIND_GUIDE
        try:
            if action == "bind":
                player = await self._service.register_identity(identity, argument)
                return copy.bind_success(player.name, player.steam_id)
            if action in {"profile", "status"}:
                result = await self._service.get_profile(identity)
                if result is None:
                    return copy.NOT_BOUND
                return copy.profile(result) if action == "profile" else copy.status(result)
            if action == "unbind":
                removed = await self._service.unregister_identity(identity)
                return copy.UNBOUND if removed else copy.UNBOUND_EMPTY
            return "监测站没有这项操作。检查一下指令。"
        except Exception as exc:
            logger.exception(
                "[STEAM] action failed | action=%s | scene_group=%s | user_id=%s",
                action, bool(identity.group_id), identity.user_id,
            )
            return copy.error_text(exc)
