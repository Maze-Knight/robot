from __future__ import annotations

import logging
import time
from typing import Any

from . import copywriting as copy
from .client import TrickcalError, TrickcalProfileNotFoundError
from .formatter import TrickcalFormatter
from .models import TrickcalIdentity

logger = logging.getLogger("elena.qq.trickcal.commands")


class TrickcalController:
    """Routes QQ interactions without embedding remote HTTP response schemas."""

    def __init__(self, service: Any | None, menus: Any, *, mode: str | None = None) -> None:
        self._service = service
        self._menus = menus
        self._mode = mode or ("local" if hasattr(service, "issue_entry") else "remote")
        self._last_action: dict[tuple[str, str], float] = {}

    async def handle_text(self, context: Any) -> bool:
        if context.content.strip().casefold() not in {"/蜡笔板", "蜡笔板"}:
            return False
        await self._menus.send_trickcal_home(context.scene_type, context.group_id or context.user_id, context.message_id)
        return True

    async def handle_interaction(self, scene: str, chat_id: str, user_id: str, button_data: str, event_id: str | None) -> None:
        if button_data == "trickcal:home":
            await self._menus.send_trickcal_home(scene, chat_id, event_id=event_id); return
        if button_data == "trickcal:back":
            await self._menus.send_services_menu(scene, chat_id, event_id=event_id); return
        if button_data == "trickcal:open":
            if not await self._allow(user_id, "open", 3.0):
                await self._menus.send_plain_text(scene, chat_id, copy.TOO_FAST, event_id=event_id); return
            if self._service is None or self._mode == "disabled":
                await self._menus.send_plain_text(scene, chat_id, copy.UNAVAILABLE, event_id=event_id); return
            try:
                url = await self._entry_url(scene, user_id)
                await self._menus.send_trickcal_login(scene, chat_id, copy.FIRST_ENTRY, url, event_id=event_id)
            except Exception:
                logger.exception("[TRICKCAL] login ticket interaction failed")
                await self._menus.send_plain_text(scene, chat_id, copy.ENTRY_FAILED, event_id=event_id)
            return
        if button_data == "trickcal:progress":
            if not await self._allow(user_id, "progress", 2.0):
                await self._menus.send_plain_text(scene, chat_id, copy.TOO_FAST, event_id=event_id); return
            if self._service is None or self._mode == "disabled":
                await self._menus.send_plain_text(scene, chat_id, copy.UNAVAILABLE, event_id=event_id); return
            if self._mode == "local":
                await self._legacy_progress(scene, chat_id, user_id, event_id)
                return
            try:
                summary = await self._service.get_summary(self._identity(scene, user_id))
            except TrickcalProfileNotFoundError:
                await self._send_empty(scene, chat_id, event_id)
                return
            except TrickcalError:
                logger.exception("[TRICKCAL] summary interaction failed")
                await self._menus.send_plain_text(scene, chat_id, copy.ENTRY_FAILED, event_id=event_id)
                return
            except Exception:
                logger.exception("[TRICKCAL] unexpected summary interaction failure")
                await self._menus.send_plain_text(scene, chat_id, copy.ENTRY_FAILED, event_id=event_id)
                return
            if summary.profile_exists is False:
                await self._send_empty(scene, chat_id, event_id)
            else:
                await self._menus.send_trickcal_home(
                    scene, chat_id, event_id=event_id, content=TrickcalFormatter.summary(summary)
                )

    @staticmethod
    def _identity(scene: str, user_id: str) -> TrickcalIdentity:
        return TrickcalIdentity(platform="qq_official", user_id=user_id, scene_type=scene)

    async def _entry_url(self, scene: str, user_id: str) -> str:
        if self._mode == "local":
            return await self._service.issue_entry(user_id)
        ticket = await self._service.create_login_ticket(self._identity(scene, user_id))
        return ticket.url

    async def _legacy_progress(self, scene: str, chat_id: str, user_id: str, event_id: str | None) -> None:
        try:
            identity = await self._service.identity(user_id)
            summary = await self._service.get_summary(identity.id)
            if summary is None:
                try:
                    url = await self._service.issue_entry(user_id)
                    await self._menus.send_trickcal_login(
                        scene, chat_id, copy.EMPTY, url, event_id=event_id
                    )
                except Exception:
                    await self._menus.send_plain_text(
                        scene, chat_id, copy.ENTRY_FAILED, event_id=event_id
                    )
            else:
                await self._menus.send_trickcal_home(scene, chat_id, event_id=event_id, content=copy.legacy_summary_text(summary))
        except Exception:
            logger.exception("[TRICKCAL] local legacy summary interaction failed")
            await self._menus.send_plain_text(scene, chat_id, copy.ENTRY_FAILED, event_id=event_id)

    async def _send_empty(self, scene: str, chat_id: str, event_id: str | None) -> None:
        send_empty = getattr(self._menus, "send_trickcal_empty", None)
        if send_empty is None:
            await self._menus.send_trickcal_home(scene, chat_id, event_id=event_id, content=copy.EMPTY)
            return
        await send_empty(scene, chat_id, event_id=event_id)

    async def _allow(self, user_id: str, action: str, window: float) -> bool:
        now = time.monotonic()
        key = (user_id, action)
        previous = self._last_action.get(key)
        if previous is not None and now - previous < window:
            return False
        self._last_action[key] = now
        return True
