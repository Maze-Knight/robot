from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx

from gifts.client import GiftApiClient
from gifts.commands import GiftController, parse_gift_command
from gifts.models import Gift, GiftPeriod, RatingRule
from gifts.service import GiftQueryService


class GiftCommandTests(unittest.TestCase):
    def test_chinese_query_commands(self) -> None:
        self.assertEqual(parse_gift_command("/礼包查询"), ("home", ""))
        self.assertEqual(parse_gift_command("/礼包排行"), ("ranking", ""))
        self.assertEqual(
            parse_gift_command("/礼包期次 第12期"), ("ranking", "第12期")
        )
        self.assertEqual(parse_gift_command("礼包 每周特惠"), ("search", "每周特惠"))
        self.assertIsNone(parse_gift_command("这不是礼包指令"))


class GiftApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_website_contract_is_parsed(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/gift-folders":
                body = {
                    "success": True,
                    "data": [
                        {
                            "id": "period-12",
                            "name": "第12期",
                            "code": "p12",
                            "folder_type": "periodic",
                            "sort_order": 12,
                            "is_enabled": True,
                            "created_at": "2026-09-01T00:00:00Z",
                        },
                        {
                            "id": "admin-folder",
                            "name": "后台草稿",
                            "folder_type": "other",
                            "is_enabled": True,
                        },
                    ],
                }
            elif request.url.path == "/api/gifts":
                self.assertEqual(request.url.params["folderId"], "period-12")
                body = {
                    "success": True,
                    "data": [
                        {
                            "id": "gift-1",
                            "name": "市长特供",
                            "price": "30.00",
                            "total_crystal_value": "90.00",
                            "cost_performance": "3.0000",
                            "rating": "recommended",
                        }
                    ],
                }
            else:
                body = {"success": True, "data": []}
            return httpx.Response(200, content=json.dumps(body).encode("utf-8"))

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            client = GiftApiClient(http, "https://gift.example.com")
            periods = await client.list_periods()
            gifts = await client.list_gifts(folder_id="period-12")

        self.assertEqual([period.name for period in periods], ["第12期"])
        self.assertEqual(gifts[0].ratio, 3.0)


class GiftServiceTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def period(name: str, created_at: str = "") -> GiftPeriod:
        return GiftPeriod("id-" + name, name, name, "periodic", 0, created_at)

    async def test_latest_period_prefers_highest_issue_number(self) -> None:
        client = SimpleNamespace(
            list_periods=AsyncMock(
                return_value=[
                    self.period("第9期", "2026-09-10T00:00:00Z"),
                    self.period("第12期", "2026-08-01T00:00:00Z"),
                    self.period("第十一期", "2026-07-01T00:00:00Z"),
                ]
            )
        )
        view = await GiftQueryService(client).periods()
        self.assertEqual(
            [period.name for period in view.periods],
            ["第12期", "第十一期", "第9期"],
        )

    async def test_ranking_separates_free_gifts_from_paid_ratio(self) -> None:
        period = self.period("第12期")
        client = SimpleNamespace(
            list_periods=AsyncMock(return_value=[period]),
            list_gifts=AsyncMock(
                return_value=[
                    Gift("paid", "付费礼包", 30, 90, 3, "good", "active", True, False, None, None, "none"),
                    Gift("free", "免费礼包", 0, 10, 999999, "great", "active", True, False, None, None, "none"),
                ]
            ),
            list_rating_rules=AsyncMock(
                return_value=[RatingRule("good", "推荐", 2, 4, 1)]
            ),
        )
        content = (await GiftQueryService(client).ranking()).content
        self.assertLess(content.index("免费礼包"), content.index("付费礼包"))
        self.assertIn("3 叶/元", content)
        self.assertNotIn("999999", content)


class GiftControllerTests(unittest.IsolatedAsyncioTestCase):
    async def test_unconfigured_source_explains_required_setting(self) -> None:
        service = SimpleNamespace(client=SimpleNamespace(configured=False))
        menus = SimpleNamespace(send_gift_view=AsyncMock())
        controller = GiftController(service, menus)
        context = SimpleNamespace(
            content="/礼包查询",
            scene_type="group",
            group_id="group-openid",
            user_id="member-openid",
            message_id="message-id",
        )

        self.assertTrue(await controller.handle_text(context))
        content = menus.send_gift_view.await_args.args[2]
        self.assertIn("GIFT_API_BASE_URL", content)


if __name__ == "__main__":
    unittest.main()
