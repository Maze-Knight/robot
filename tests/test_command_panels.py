from __future__ import annotations

import unittest
from typing import Any

from command_panels import (
    CommandPanelSynchronizer,
    PANEL_ITEMS,
    PANEL_REMARK,
    panel_definition,
)


class FakeApi:
    def __init__(self, records: dict[str, list[dict[str, Any]]] | None = None) -> None:
        self.records = records or {"group": [], "c2c": []}
        self.calls: list[tuple[str, str, dict[str, Any] | None]] = []

    async def request(
        self, method: str, path: str, body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        self.calls.append((method, path, body))
        if method == "GET":
            scope = path.split("scope=", 1)[1].split("&", 1)[0]
            return {"records": self.records[scope]}
        return {}


def managed_record(scope: str, panel: dict[str, Any]) -> dict[str, Any]:
    return {
        "panel_id": f"{scope}-panel-id",
        "scope": scope,
        "target_type": "all",
        "panel": panel,
    }


class CommandPanelSynchronizerTests(unittest.IsolatedAsyncioTestCase):
    async def test_creates_group_and_c2c_panels_when_absent(self) -> None:
        api = FakeApi()

        await CommandPanelSynchronizer(api).sync_all()

        creates = [call for call in api.calls if call[0] == "POST"]
        self.assertEqual(len(creates), 2)
        self.assertEqual({call[2]["scope"] for call in creates}, {"group", "c2c"})
        for _, path, body in creates:
            self.assertEqual(path, "/v2/panels")
            self.assertEqual(body["target_type"], "all")
            self.assertEqual(body["panel"], panel_definition())

    async def test_current_managed_panels_are_not_rewritten(self) -> None:
        definition = panel_definition()
        api = FakeApi(
            {
                scope: [managed_record(scope, definition)]
                for scope in ("group", "c2c")
            }
        )

        await CommandPanelSynchronizer(api).sync_all()

        self.assertEqual([call[0] for call in api.calls], ["GET", "GET"])

    async def test_updates_stale_managed_panel_without_touching_other_panels(self) -> None:
        stale = panel_definition()
        stale["items"] = stale["items"][:1]
        api = FakeApi(
            {
                "group": [
                    {"panel_id": "unrelated", "scope": "group", "target_type": "all", "panel": {"remark": "other", "items": []}},
                    managed_record("group", stale),
                ],
                "c2c": [],
            }
        )

        await CommandPanelSynchronizer(api).sync_scope("group")

        self.assertEqual(
            api.calls,
            [
                ("GET", "/v2/panels?scope=group&limit=50", None),
                ("PUT", "/v2/panels/group-panel-id", {"panel": panel_definition()}),
            ],
        )

    def test_definition_keeps_all_seven_public_commands(self) -> None:
        self.assertEqual(PANEL_REMARK, "elena-command-panel-v1")
        self.assertEqual(
            [item["name"] for item in PANEL_ITEMS],
            ["菜单", "蜡笔板", "蜡笔进度", "礼包查询", "每日单抽", "雀魂", "帮助"],
        )
        self.assertTrue(all(item["only_admin"] is False for item in PANEL_ITEMS))
