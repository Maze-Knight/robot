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

    def __init__(
        self,
        service: Any | None,
        menus: Any,
        *,
        mode: str | None = None,
        progress_card_renderer: Any = None,
    ) -> None:
        self._service = service
        self._menus = menus
        self._mode = mode or ("local" if hasattr(service, "issue_entry") else "remote")
        self._progress_card_renderer = progress_card_renderer
        self._last_action: dict[tuple[str, str], float] = {}

    async def handle_text(self, context: Any) -> bool:
        command = context.content.strip().casefold()
        scene = context.scene_type
        chat_id = context.group_id or context.user_id
        if command in {"/蜡笔板", "蜡笔板"}:
            await self._menus.send_trickcal_home(
                scene,
                chat_id,
                context.message_id,
                content=self._address(scene, context.user_id, copy.HOME),
            )
            return True
        if command == "/打开蜡笔板":
            await self._handle_text_open(context, scene, chat_id)
            return True
        if command == "/蜡笔板进度":
            await self._handle_text_progress(context, scene, chat_id)
            return True
        return False

    async def _handle_text_open(self, context: Any, scene: str, chat_id: str) -> None:
        if not await self._allow(context.user_id, "open", 3.0):
            await context.reply(self._address(scene, context.user_id, copy.TOO_FAST))
            return
        if self._service is None or self._mode == "disabled":
            await context.reply(self._address(scene, context.user_id, copy.UNAVAILABLE))
            return
        try:
            url = await self._entry_url(scene, context.user_id)
            await self._menus.send_trickcal_login(
                scene,
                chat_id,
                self._address(scene, context.user_id, copy.FIRST_ENTRY),
                url,
                reply_to=context.message_id,
            )
        except Exception:
            logger.exception("[TRICKCAL] login ticket command failed")
            await context.reply(self._address(scene, context.user_id, copy.ENTRY_FAILED))

    async def _handle_text_progress(self, context: Any, scene: str, chat_id: str) -> None:
        if not await self._allow(context.user_id, "progress", 2.0):
            await context.reply(self._address(scene, context.user_id, copy.TOO_FAST))
            return
        if self._service is None or self._mode == "disabled":
            await context.reply(self._address(scene, context.user_id, copy.UNAVAILABLE))
            return
        if self._mode == "local":
            await self._legacy_progress(scene, chat_id, context.user_id, None)
            return
        try:
            summary = await self._service.get_summary(self._identity(scene, context.user_id))
        except TrickcalProfileNotFoundError:
            await self._menus.send_trickcal_empty(
                scene,
                chat_id,
                reply_to=context.message_id,
                content=self._address(scene, context.user_id, copy.EMPTY),
            )
            return
        except TrickcalError:
            logger.exception("[TRICKCAL] summary command failed")
            await context.reply(self._address(scene, context.user_id, copy.ENTRY_FAILED))
            return
        except Exception:
            logger.exception("[TRICKCAL] unexpected summary command failure")
            await context.reply(self._address(scene, context.user_id, copy.ENTRY_FAILED))
            return
        if summary.profile_exists is False:
            await self._menus.send_trickcal_empty(
                scene,
                chat_id,
                reply_to=context.message_id,
                content=self._address(scene, context.user_id, copy.EMPTY),
            )
            return
        await self._send_text_progress(context, scene, chat_id, summary)

    async def _send_text_progress(
        self, context: Any, scene: str, chat_id: str, summary: Any
    ) -> None:
        content = TrickcalFormatter.summary(summary)
        if self._progress_card_renderer is not None and len(summary.attribute_stats) == 5:
            try:
                image = self._progress_card_renderer.render(summary)
                await self._menus.send_image(
                    scene,
                    chat_id,
                    image,
                    reply_to=context.message_id,
                    file_name="trickcal-progress.png",
                )
                content = copy.PROGRESS_CARD_READY
            except Exception:
                logger.exception("[TRICKCAL] progress card failed; falling back to text")
        await self._menus.send_trickcal_home(
            scene,
            chat_id,
            reply_to=context.message_id,
            content=self._address(scene, context.user_id, content),
        )

    async def handle_interaction(self, scene: str, chat_id: str, user_id: str, button_data: str, event_id: str | None) -> None:
        if button_data == "trickcal:home":
            await self._menus.send_trickcal_home(
                scene, chat_id, event_id=event_id, content=self._address(scene, user_id, copy.HOME)
            ); return
        if button_data == "trickcal:back":
            await self._menus.send_services_menu(scene, chat_id, event_id=event_id); return
        if button_data == "trickcal:open":
            if not await self._allow(user_id, "open", 3.0):
                await self._menus.send_plain_text(scene, chat_id, self._address(scene, user_id, copy.TOO_FAST), event_id=event_id); return
            if self._service is None or self._mode == "disabled":
                await self._menus.send_plain_text(scene, chat_id, self._address(scene, user_id, copy.UNAVAILABLE), event_id=event_id); return
            try:
                url = await self._entry_url(scene, user_id)
                await self._menus.send_trickcal_login(
                    scene, chat_id, self._address(scene, user_id, copy.FIRST_ENTRY), url, event_id=event_id
                )
            except Exception:
                logger.exception("[TRICKCAL] login ticket interaction failed")
                await self._menus.send_plain_text(scene, chat_id, self._address(scene, user_id, copy.ENTRY_FAILED), event_id=event_id)
            return
        if button_data == "trickcal:progress":
            if not await self._allow(user_id, "progress", 2.0):
                await self._menus.send_plain_text(scene, chat_id, self._address(scene, user_id, copy.TOO_FAST), event_id=event_id); return
            if self._service is None or self._mode == "disabled":
                await self._menus.send_plain_text(scene, chat_id, self._address(scene, user_id, copy.UNAVAILABLE), event_id=event_id); return
            if self._mode == "local":
                await self._legacy_progress(scene, chat_id, user_id, event_id)
                return
            try:
                summary = await self._service.get_summary(self._identity(scene, user_id))
            except TrickcalProfileNotFoundError:
                await self._send_empty(scene, chat_id, user_id, event_id)
                return
            except TrickcalError:
                logger.exception("[TRICKCAL] summary interaction failed")
                await self._menus.send_plain_text(scene, chat_id, self._address(scene, user_id, copy.ENTRY_FAILED), event_id=event_id)
                return
            except Exception:
                logger.exception("[TRICKCAL] unexpected summary interaction failure")
                await self._menus.send_plain_text(scene, chat_id, self._address(scene, user_id, copy.ENTRY_FAILED), event_id=event_id)
                return
            if summary.profile_exists is False:
                await self._send_empty(scene, chat_id, user_id, event_id)
            else:
                await self._menus.send_trickcal_home(
                    scene, chat_id, event_id=event_id,
                    content=self._address(scene, user_id, TrickcalFormatter.summary(summary))
                )

    @staticmethod
    def _identity(scene: str, user_id: str) -> TrickcalIdentity:
        return TrickcalIdentity(platform="qq_official", user_id=user_id, scene_type=scene)

    @staticmethod
    def _address(scene: str, user_id: str, content: str) -> str:
        """Make group responses unambiguous without adding noise to direct messages."""
        if scene == "group" and user_id:
            return f"<@{user_id}>\n{content}"
        return content

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
                        scene, chat_id, self._address(scene, user_id, copy.EMPTY), url, event_id=event_id
                    )
                except Exception:
                    await self._menus.send_plain_text(
                        scene, chat_id, self._address(scene, user_id, copy.ENTRY_FAILED), event_id=event_id
                    )
            else:
                await self._menus.send_trickcal_home(
                    scene,
                    chat_id,
                    event_id=event_id,
                    content=self._address(scene, user_id, copy.legacy_summary_text(summary)),
                )
        except Exception:
            logger.exception("[TRICKCAL] local legacy summary interaction failed")
            await self._menus.send_plain_text(
                scene, chat_id, self._address(scene, user_id, copy.ENTRY_FAILED), event_id=event_id
            )

    async def _send_empty(self, scene: str, chat_id: str, user_id: str, event_id: str | None) -> None:
        send_empty = getattr(self._menus, "send_trickcal_empty", None)
        if send_empty is None:
            await self._menus.send_trickcal_home(
                scene, chat_id, event_id=event_id, content=self._address(scene, user_id, copy.EMPTY)
            )
            return
        await send_empty(scene, chat_id, event_id=event_id, content=self._address(scene, user_id, copy.EMPTY))

    async def _allow(self, user_id: str, action: str, window: float) -> bool:
        now = time.monotonic()
        key = (user_id, action)
        previous = self._last_action.get(key)
        if previous is not None and now - previous < window:
            return False
        self._last_action[key] = now
        return True
