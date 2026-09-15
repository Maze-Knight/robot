from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

from daily_draw.catalog import DrawCatalog
from daily_draw.card import DailyDrawCardRenderer
from daily_draw.commands import DailyDrawController, parse_draw_command
from daily_draw.engine import DrawEngine
from daily_draw.models import CollectionEntry, CollectionSnapshot, DrawIdentity
from daily_draw.repository import DrawRepository
from daily_draw.service import DailyDrawService
from PIL import Image


class FakeRandom:
    def __init__(self, choices: list[int] | None = None) -> None:
        self.choices = iter(choices or [0] * 100)

    def choice(self, sequence: tuple[object, ...]) -> object:
        return sequence[next(self.choices) % len(sequence)]


def write_pool(path: Path, *, ready: bool = True) -> DrawCatalog:
    payload = {
        "pool_id": "test-uniform-v1",
        "items": [
            {"id": "one", "name": "测试使徒一", "image": "one.png"},
            {"id": "two", "name": "测试使徒二", "image": "two.png"},
        ] if ready else [],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return DrawCatalog.load(path)


class DrawEngineTests(unittest.TestCase):
    def test_ten_pull_uses_one_uniform_pool(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            catalog = write_pool(Path(folder) / "pool.json")
            engine = DrawEngine(FakeRandom(list(range(10))))
            result = engine.draw_ten(catalog)
        self.assertEqual(len(result), 10)
        self.assertEqual([item.item_id for item in result], ["one", "two"] * 5)

    def test_renderer_builds_ten_pull_png_with_portraits(self) -> None:
        from daily_draw.models import DrawItem, DrawRecord

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            Image.new("RGB", (252, 252), "#ff99aa").save(root / "portrait.png")
            item = DrawItem("test", "测试使徒", "portrait.png")
            record = DrawRecord(
                DrawIdentity("qq_official", "member"),
                "2026-09-15",
                (item,) * 10,
                "2026-09-15T12:00:00+08:00",
            )
            rendered = DailyDrawCardRenderer(root).render(record)
            with Image.open(__import__("io").BytesIO(rendered)) as image:
                self.assertEqual(image.size, (1000, 650))
                self.assertEqual(image.format, "PNG")

    def test_renderer_builds_complete_collection_grid(self) -> None:
        from daily_draw.models import DrawItem

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            Image.new("RGB", (252, 252), "#ff99aa").save(root / "portrait.png")
            entries = tuple(
                CollectionEntry(
                    DrawItem(str(index), f"使徒{index}", "portrait.png"),
                    2 if index < 3 else 0,
                )
                for index in range(78)
            )
            snapshot = CollectionSnapshot(
                DrawIdentity("qq_official", "member"), entries
            )
            rendered = DailyDrawCardRenderer(root).render_collection(snapshot)
            with Image.open(__import__("io").BytesIO(rendered)) as image:
                self.assertGreaterEqual(image.width, 1700)
                self.assertGreaterEqual(image.height, 900)
                self.assertEqual(image.format, "PNG")


class DailyDrawServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_empty_pool_does_not_consume_daily_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            repository = DrawRepository(root / "draw.sqlite3")
            await repository.initialize()
            service = DailyDrawService(
                write_pool(root / "pool.json", ready=False), repository
            )
            identity = DrawIdentity("qq_official", "member", "group")
            outcome = await service.draw(identity)
            stored = await service.get_today(identity)
        self.assertEqual(outcome.state, "pool_not_ready")
        self.assertIsNone(stored)

    async def test_second_ten_pull_returns_first_record(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            repository = DrawRepository(root / "draw.sqlite3")
            await repository.initialize()
            catalog = write_pool(root / "pool.json")
            service = DailyDrawService(
                catalog, repository, DrawEngine(FakeRandom())
            )
            identity = DrawIdentity("qq_official", "member", "group")
            first = await service.draw(identity)
            second = await service.draw(identity)
            collection = await service.collection(identity)
        self.assertEqual(first.state, "drawn")
        self.assertEqual(second.state, "already_drawn")
        self.assertEqual(first.record, second.record)
        self.assertEqual(len(first.updates), 1)
        self.assertEqual(first.updates[0].copies, 10)
        self.assertEqual(first.updates[0].current_stars, 10)
        self.assertEqual(collection.unlocked_count, 1)
        self.assertEqual(collection.entries[0].copies, 10)

    async def test_group_scoped_history_migrates_to_user_collection(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            repository = DrawRepository(root / "draw.sqlite3")
            await repository.initialize()
            catalog = write_pool(root / "pool.json")
            old_service = DailyDrawService(
                catalog, repository, DrawEngine(FakeRandom())
            )
            await old_service.draw(DrawIdentity("qq_official", "member", "old-group"))

            migrated_repository = DrawRepository(root / "draw.sqlite3")
            await migrated_repository.initialize()
            service = DailyDrawService(catalog, migrated_repository)
            identity = DrawIdentity("qq_official", "member")
            record = await service.get_today(identity)
            collection = await service.collection(identity)

        self.assertIsNotNone(record)
        self.assertEqual(collection.unlocked_count, 1)
        self.assertEqual(collection.entries[0].copies, 10)

    async def test_pool_change_clears_old_draws_and_collection(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            repository = DrawRepository(root / "draw.sqlite3")
            await repository.initialize()
            catalog = write_pool(root / "pool.json")
            await repository.ensure_pool_version(catalog.pool_id)
            service = DailyDrawService(catalog, repository, DrawEngine(FakeRandom()))
            identity = DrawIdentity("qq_official", "member")
            await service.draw(identity)

            changed = await repository.ensure_pool_version("replacement-pool-v2")
            stored = await service.get_today(identity)
            collection = await service.collection(identity)

        self.assertTrue(changed)
        self.assertIsNone(stored)
        self.assertEqual(collection.unlocked_count, 0)


class DailyDrawControllerTests(unittest.IsolatedAsyncioTestCase):
    def test_commands_are_chinese(self) -> None:
        self.assertEqual(parse_draw_command("/每日抽取"), "draw")
        self.assertEqual(parse_draw_command("/进行十连"), "draw")
        self.assertEqual(parse_draw_command("/抽取记录"), "record")
        self.assertEqual(parse_draw_command("/图鉴"), "collection")
        self.assertIsNone(parse_draw_command("/daily draw"))

    async def test_empty_pool_message_uses_menu_and_does_not_write(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            repository = DrawRepository(root / "draw.sqlite3")
            await repository.initialize()
            service = DailyDrawService(
                write_pool(root / "pool.json", ready=False), repository
            )
            menus = AsyncMock()
            controller = DailyDrawController(service, menus)
            context = type(
                "Context",
                (),
                {
                    "content": "/进行十连",
                    "platform": "qq_official",
                    "user_id": "member",
                    "group_id": "group",
                    "scene_type": "group",
                    "message_id": "message",
                },
            )()
            handled = await controller.handle_text(context)
        self.assertTrue(handled)
        menus.send_daily_draw_view.assert_awaited_once()
        self.assertIn("不消耗今日次数", menus.send_daily_draw_view.await_args.args[2])


if __name__ == "__main__":
    unittest.main()
