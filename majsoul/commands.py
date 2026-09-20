from __future__ import annotations

import logging
import time
from typing import Any

from . import copywriting as copy
from .client import (
    MajsoulError,
    MajsoulNotFoundError,
    MajsoulRateLimitError,
)
from .models import MajsoulIdentity, PlayerCandidate, rank_label
from .service import MajsoulBindingNotFoundError, MajsoulService


logger = logging.getLogger("elena.qq.majsoul")


def parse_majsoul_command(content: str) -> tuple[str, str] | None:
    text = content.strip()
    lowered = text.casefold()
    if lowered in {"雀魂服务", "/雀魂服务"}:
        return "home", ""
    if lowered in {"雀魂", "/雀魂", "雀魂档案", "/雀魂档案", "我的雀魂", "/我的雀魂"}:
        return "profile", ""
    if lowered in {"雀魂四麻", "/雀魂四麻"}:
        return "profile", "four"
    if lowered in {"雀魂三麻", "/雀魂三麻"}:
        return "profile", "three"
    if lowered in {"登记雀魂", "/登记雀魂", "身份登记", "/身份登记"}:
        return "register", ""
    if lowered in {"解绑雀魂", "/解绑雀魂"}:
        return "unbind", ""
    for prefix in ("绑定雀魂 ", "/绑定雀魂 "):
        if text.startswith(prefix):
            nickname = text[len(prefix):].strip()
            return "bind", nickname
    return None


class MajsoulController:
    def __init__(self, service: MajsoulService, menus: Any, renderer: Any) -> None:
        self._service = service
        self._menus = menus
        self._renderer = renderer
        self._candidates: dict[tuple[str, str, str], tuple[float, PlayerCandidate]] = {}
        self._last_action: dict[tuple[str, str], float] = {}

    async def handle_text(self, context: Any) -> bool:
        parsed = parse_majsoul_command(context.content)
        if parsed is None:
            return False
        action, argument = parsed
        identity = self._identity(context.scene_type, context.user_id)
        chat_id = context.group_id or context.user_id
        if action == "home":
            await self._menus.send_majsoul_home(context.scene_type, chat_id, copy.HOME, reply_to=context.message_id)
            return True
        if action == "register":
            await self._menus.send_majsoul_home(context.scene_type, chat_id, copy.REGISTER, reply_to=context.message_id)
            return True
        if action == "unbind":
            removed = await self._service.unbind(identity)
            await context.reply(copy.UNBOUND_DONE if removed else copy.UNBOUND)
            return True
        if action == "bind":
            if not argument:
                await self._menus.send_majsoul_home(context.scene_type, chat_id, copy.REGISTER, reply_to=context.message_id)
                return True
            await self._search_and_offer(context.scene_type, chat_id, context.user_id, identity, argument, context.message_id)
            return True
        await self._show_profile(context.scene_type, chat_id, context.user_id, identity, context.message_id, argument or None)
        return True

    async def handle_interaction(self, scene: str, chat_id: str, user_id: str, button_data: str, event_id: str | None) -> None:
        identity = self._identity(scene, user_id)
        if button_data == "majsoul:home":
            await self._menus.send_majsoul_home(scene, chat_id, copy.HOME, event_id=event_id)
            return
        if button_data == "majsoul:back":
            await self._menus.send_services_menu(scene, chat_id, event_id=event_id)
            return
        if button_data == "majsoul:register":
            await self._menus.send_majsoul_home(scene, chat_id, copy.REGISTER, event_id=event_id)
            return
        if button_data == "majsoul:profile":
            await self._show_profile(scene, chat_id, user_id, identity, None, None, event_id=event_id)
            return
        if button_data.startswith("majsoul:bind:"):
            player_id = button_data.removeprefix("majsoul:bind:")
            candidate = self._take_candidate(scene, user_id, player_id)
            if candidate is None:
                await self._menus.send_plain_text(scene, chat_id, "候选档案已过期。重新发送“绑定雀魂 玩家昵称”。", event_id=event_id)
                return
            binding = await self._service.bind(identity, candidate)
            content = f"身份登记完成。\n\n雀魂：{binding.nickname}\n段位：{rank_label(binding.level_id)}\n\n很好，至少这次档案没认错人。"
            await self._menus.send_majsoul_home(scene, chat_id, content, event_id=event_id)

    async def _search_and_offer(self, scene: str, chat_id: str, user_id: str, identity: MajsoulIdentity, nickname: str, reply_to: str) -> None:
        try:
            candidates = await self._service.search(nickname)
        except MajsoulRateLimitError:
            await self._menus.send_plain_text(scene, chat_id, copy.RATE_LIMIT)
            return
        except MajsoulError:
            logger.exception("[MAJSOUL] player search failed")
            await self._menus.send_plain_text(scene, chat_id, copy.UNAVAILABLE)
            return
        exact = [candidate for candidate in candidates if candidate.nickname.casefold() == nickname.casefold()]
        offered = exact or list(candidates[:5])
        if not offered:
            await self._menus.send_majsoul_home(scene, chat_id, copy.NO_PLAYER, reply_to=reply_to)
            return
        if len(offered) == 1:
            binding = await self._service.bind(identity, offered[0])
            content = f"身份登记完成。\n\n雀魂：{binding.nickname}\n段位：{rank_label(binding.level_id)}\n\n很好，至少这次档案没认错人。"
            await self._menus.send_majsoul_home(scene, chat_id, content, reply_to=reply_to)
            return
        for candidate in offered:
            self._candidates[(scene, user_id, candidate.player_id)] = (time.monotonic() + 600.0, candidate)
        lines = [copy.MULTIPLE, ""]
        lines.extend(f"{index}. {candidate.nickname} · {rank_label(candidate.level_id)}" for index, candidate in enumerate(offered, start=1))
        await self._menus.send_majsoul_candidates(scene, chat_id, "\n".join(lines), offered, reply_to=reply_to)

    async def _show_profile(self, scene: str, chat_id: str, user_id: str, identity: MajsoulIdentity, reply_to: str | None, family: str | None, *, event_id: str | None = None) -> None:
        if not self._allow(user_id, "profile", 3.0):
            await self._menus.send_plain_text(scene, chat_id, copy.TOO_FAST, event_id=event_id)
            return
        try:
            profile = await self._service.profile(identity, family)
        except MajsoulBindingNotFoundError:
            await self._menus.send_majsoul_home(scene, chat_id, copy.UNBOUND, reply_to=reply_to, event_id=event_id)
            return
        except MajsoulNotFoundError:
            await self._menus.send_plain_text(scene, chat_id, copy.NO_GAMES, event_id=event_id)
            return
        except MajsoulRateLimitError:
            await self._menus.send_plain_text(scene, chat_id, copy.RATE_LIMIT, event_id=event_id)
            return
        except MajsoulError:
            logger.exception("[MAJSOUL] profile request failed")
            await self._menus.send_plain_text(scene, chat_id, copy.UNAVAILABLE, event_id=event_id)
            return
        image = self._renderer.render(profile)
        await self._menus.send_plain_text(scene, chat_id, "档案生成完毕。", event_id=event_id)
        await self._menus.send_image(scene, chat_id, image, reply_to=reply_to or "", file_name="majsoul_profile.png")

    def _take_candidate(self, scene: str, user_id: str, player_id: str) -> PlayerCandidate | None:
        item = self._candidates.pop((scene, user_id, player_id), None)
        if item is None or item[0] < time.monotonic():
            return None
        return item[1]

    @staticmethod
    def _identity(scene: str, user_id: str) -> MajsoulIdentity:
        return MajsoulIdentity("qq_official", user_id, scene)

    def _allow(self, user_id: str, action: str, window: float) -> bool:
        now = time.monotonic()
        key = (user_id, action)
        prior = self._last_action.get(key)
        if prior is not None and now - prior < window:
            return False
        self._last_action[key] = now
        return True
