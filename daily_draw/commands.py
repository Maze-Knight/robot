from __future__ import annotations

import logging
from typing import Any

from . import copywriting as copy
from .models import DrawIdentity
from .service import DailyDrawService


logger = logging.getLogger("elena.qq.daily_draw")


def parse_draw_command(content: str) -> str | None:
    command = content.strip().casefold()
    commands = {
        "每日抽取": "draw",
        "/每日抽取": "draw",
        "进行十连": "draw",
        "/进行十连": "draw",
        "今日抽取": "record",
        "/今日抽取": "record",
        "抽取记录": "record",
        "/抽取记录": "record",
        "图鉴": "collection",
        "/图鉴": "collection",
    }
    return commands.get(command)


class DailyDrawController:
    def __init__(self, service: DailyDrawService, menus: Any, renderer: Any = None) -> None:
        self._service = service
        self._menus = menus
        self._renderer = renderer

    async def handle_text(self, context: Any) -> bool:
        action = parse_draw_command(context.content)
        if action is None:
            return False
        # QQ Official openid/member_openid is the only trustworthy user key.
        # Keep the collection user-scoped instead of creating one per group.
        identity = DrawIdentity(context.platform, context.user_id)
        chat_id = context.group_id or context.user_id
        outcome_record = None
        snapshot = None
        if action == "home":
            content = copy.HOME if self._service.catalog.ready else copy.POOL_NOT_READY
        elif action == "collection":
            snapshot = await self._service.collection(identity)
            content = copy.collection_text(snapshot)
        elif action == "record":
            record = await self._service.get_today(identity)
            content = copy.record_text(record, already_drawn=True) if record else copy.NO_RECORD
            outcome_record = record
        else:
            outcome = await self._service.draw(identity)
            if outcome.state == "pool_not_ready":
                content = copy.POOL_NOT_READY
            else:
                assert outcome.record is not None
                content = copy.record_text(
                    outcome.record,
                    already_drawn=outcome.state == "already_drawn",
                    updates=outcome.updates,
                )
                outcome_record = outcome.record
        if outcome_record is not None:
            if self._renderer is not None:
                try:
                    image = self._renderer.render(outcome_record)
                    await self._menus.send_image(
                        context.scene_type,
                        chat_id,
                        image,
                        reply_to=context.message_id,
                    )
                except Exception:
                    # The complete text result is still sent if image rendering or
                    # upload has a transient failure.
                    logger.exception(
                        "[DAILY_DRAW] result card failed | scene=%s | message_id=%s",
                        context.scene_type,
                        context.message_id,
                    )
        if snapshot is not None and self._renderer is not None:
            try:
                image = self._renderer.render_collection(snapshot)
                await self._menus.send_image(
                    context.scene_type,
                    chat_id,
                    image,
                    reply_to=context.message_id,
                )
            except Exception:
                logger.exception(
                    "[DAILY_DRAW] collection card failed | scene=%s | message_id=%s",
                    context.scene_type,
                    context.message_id,
                )
        send_view = (
            self._menus.send_collection_view
            if action == "collection"
            else self._menus.send_daily_draw_view
        )
        await send_view(
            context.scene_type,
            chat_id,
            content,
            reply_to=context.message_id,
        )
        return True
