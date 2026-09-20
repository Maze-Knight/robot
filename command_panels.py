from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any


logger = logging.getLogger("elena.qq.command_panels")


PANEL_REMARK = "elena-command-panel-v1"
PANEL_SCOPES = ("group", "c2c")
PANEL_ITEMS: tuple[dict[str, Any], ...] = (
    {
        "type": "command",
        "name": "菜单",
        "desc": "打开莫纳提姆市政终端",
        "only_admin": False,
    },
    {
        "type": "command",
        "name": "蜡笔板",
        "desc": "进入个人蜡笔板",
        "only_admin": False,
    },
    {
        "type": "command",
        "name": "蜡笔进度",
        "desc": "查看当前节点进度",
        "only_admin": False,
    },
    {
        "type": "command",
        "name": "礼包查询",
        "desc": "查询礼包性价比",
        "only_admin": False,
    },
    {
        "type": "command",
        "name": "每日单抽",
        "desc": "抽取今日使徒",
        "only_admin": False,
    },
    {
        "type": "command",
        "name": "雀魂",
        "desc": "查看雀魂玩家档案",
        "only_admin": False,
    },
    {
        "type": "command",
        "name": "帮助",
        "desc": "查看终端使用说明",
        "only_admin": False,
    },
)


def panel_definition() -> dict[str, Any]:
    """Build a fresh desired panel payload without sharing mutable dictionaries."""
    return {
        "items": [dict(item) for item in PANEL_ITEMS],
        "remark": PANEL_REMARK,
    }


def _matches_definition(panel: Any) -> bool:
    if not isinstance(panel, Mapping) or panel.get("remark") != PANEL_REMARK:
        return False
    items = panel.get("items")
    if not isinstance(items, list) or len(items) != len(PANEL_ITEMS):
        return False
    for current, desired in zip(items, PANEL_ITEMS):
        if not isinstance(current, Mapping):
            return False
        if (
            current.get("type") != desired["type"]
            or current.get("name") != desired["name"]
            or current.get("desc") != desired["desc"]
            or bool(current.get("only_admin", False)) != desired["only_admin"]
        ):
            return False
    return True


class CommandPanelSynchronizer:
    """Idempotently keep Elena's official QQ command panels current.

    The official Python SDK does not yet wrap the `/v2/panels` OpenAPI.  It
    does expose an authenticated generic request method, so this intentionally
    small adapter uses that existing client rather than introducing a second
    token or HTTP stack.
    """

    def __init__(self, api: Any) -> None:
        self._api = api

    async def sync_all(self) -> None:
        for scope in PANEL_SCOPES:
            await self.sync_scope(scope)

    async def sync_scope(self, scope: str) -> None:
        if scope not in PANEL_SCOPES:
            raise ValueError(f"unsupported command panel scope: {scope}")

        listing = await self._api.request(
            "GET", f"/v2/panels?scope={scope}&limit=50"
        )
        records = listing.get("records", []) if isinstance(listing, Mapping) else []
        managed = [
            record
            for record in records
            if isinstance(record, Mapping)
            and record.get("scope") == scope
            and record.get("target_type") == "all"
            and isinstance(record.get("panel"), Mapping)
            and record["panel"].get("remark") == PANEL_REMARK
        ]

        if not managed:
            await self._api.request(
                "POST",
                "/v2/panels",
                {
                    "scope": scope,
                    "target_type": "all",
                    "panel": panel_definition(),
                },
            )
            logger.info("[COMMAND_PANEL] created | scope=%s | items=%d", scope, len(PANEL_ITEMS))
            return

        selected = managed[0]
        panel_id = str(selected.get("panel_id", "")).strip()
        if not panel_id:
            raise RuntimeError(f"[COMMAND_PANEL] managed panel missing id | scope={scope}")
        if len(managed) > 1:
            logger.warning(
                "[COMMAND_PANEL] duplicate managed panels found; keeping extras untouched | scope=%s | count=%d",
                scope,
                len(managed),
            )

        if _matches_definition(selected.get("panel")):
            logger.info("[COMMAND_PANEL] already current | scope=%s", scope)
            return

        await self._api.request(
            "PUT", f"/v2/panels/{panel_id}", {"panel": panel_definition()}
        )
        logger.info("[COMMAND_PANEL] updated | scope=%s | items=%d", scope, len(PANEL_ITEMS))
