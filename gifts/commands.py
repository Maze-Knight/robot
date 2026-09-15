from __future__ import annotations

import logging
import re
from typing import Any

from . import copywriting as copy
from .client import GiftApiError
from .service import GiftQueryService, GiftView


logger = logging.getLogger("elena.qq.gifts")


def parse_gift_command(content: str) -> tuple[str, str] | None:
    text = content.strip()
    lowered = text.casefold()
    if lowered in {"礼包", "/礼包"}:
        return "home", ""
    if lowered in {"礼包查询", "/礼包查询"}:
        return "ranking", ""
    if lowered in {"礼包期次", "/礼包期次"}:
        return "periods", "1"
    if lowered in {"礼包列表", "/礼包列表"}:
        return "periods", "1"
    if lowered in {"礼包排行", "/礼包排行"}:
        return "ranking", ""
    if lowered in {"礼包搜索", "/礼包搜索", "礼包搜索说明", "/礼包搜索说明"}:
        return "search_guide", ""
    matched = re.fullmatch(r"/?礼包列表\s+(\d+)", text, re.I)
    if matched:
        return "periods", matched.group(1)
    matched = re.fullmatch(r"/?礼包期次\s+(.+)", text, re.I)
    if matched:
        return "ranking", matched.group(1).strip()
    matched = re.fullmatch(r"/?礼包排行\s+(.+)", text, re.I)
    if matched:
        return "ranking", matched.group(1).strip()
    matched = re.fullmatch(r"/?(?:礼包搜索|礼包)\s+(.+)", text, re.I)
    if matched:
        return "search", matched.group(1).strip()
    return None


class GiftController:
    def __init__(self, service: GiftQueryService, menus: Any) -> None:
        self._service = service
        self._menus = menus

    async def handle_text(self, context: Any) -> bool:
        parsed = parse_gift_command(context.content)
        if parsed is None:
            return False
        action, argument = parsed
        chat_id = context.group_id or context.user_id
        if not self._service.client.configured:
            await self._menus.send_gift_view(
                context.scene_type,
                chat_id,
                copy.NOT_CONFIGURED,
                reply_to=context.message_id,
            )
            return True
        try:
            if action == "home":
                view = await self._service.home()
            elif action == "periods":
                view = await self._service.periods(int(argument or "1"))
            elif action == "ranking":
                view = await self._service.ranking(argument)
            elif action == "search_guide":
                view = GiftView(copy.SEARCH_GUIDE)
            else:
                view = await self._service.search(argument)
            await self._menus.send_gift_view(
                context.scene_type,
                chat_id,
                view.content,
                periods=view.periods,
                period_page=view.period_page,
                period_total_pages=view.period_total_pages,
                reply_to=context.message_id,
            )
        except GiftApiError as exc:
            logger.warning("[GIFT] query failed | action=%s | reason=%s", action, exc)
            await context.reply(copy.error_text(str(exc)))
        except Exception:
            logger.exception("[GIFT] unexpected query failure | action=%s", action)
            await context.reply(copy.error_text("未预期的数据故障"))
        return True
