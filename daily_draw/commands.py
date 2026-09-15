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
        "每日抽取": "home",
        "/每日抽取": "home",
        "进行十连": "draw",
        "/进行十连": "draw",
        "今日抽取": "record",
        "/今日抽取": "record",
        "抽取记录": "record",
        "/抽取记录": "record",
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
        identity = DrawIdentity(
            context.platform, context.user_id, context.group_id or ""
        )
        chat_id = context.group_id or context.user_id
        if action == "home":
            content = copy.HOME if self._service.catalog.ready else copy.POOL_NOT_READY
        elif action == "record":
            record = await self._service.get_today(identity)
            content = copy.record_text(record, already_drawn=True) if record else copy.NO_RECORD
        else:
            outcome = await self._service.draw(identity)
            if outcome.state == "pool_not_ready":
                content = copy.POOL_NOT_READY
            else:
                assert outcome.record is not None
                content = copy.record_text(
                    outcome.record, already_drawn=outcome.state == "already_drawn"
                )
        if outcome_record := (
            record if action == "record" and record else
            outcome.record if action == "draw" and outcome.record else None
        ):
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
        await self._menus.send_daily_draw_view(
            context.scene_type,
            chat_id,
            content,
            reply_to=context.message_id,
        )
        return True
