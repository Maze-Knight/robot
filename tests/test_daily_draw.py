from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from daily_draw.catalog import DrawCatalog
from daily_draw.card import DailyDrawCardRenderer
from daily_draw.commands import DailyDrawController, parse_draw_command
from daily_draw.engine import DrawEngine
from daily_draw.models import CollectionEntry, CollectionSnapshot, DrawIdentity
from daily_draw.repository import DrawRepository
from daily_draw.service import DailyDrawService
from PIL import Image
from ui.keyboards import build_daily_draw_keyboard


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
    def test_single_pull_uses_one_uniform_pool(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            catalog = write_pool(Path(folder) / "pool.json")
            engine = DrawEngine(FakeRandom([1]))
            result = engine.draw_one(catalog)
        self.assertEqual(result.item_id, "two")

    def test_renderer_builds_single_pull_png_with_portrait(self) -> None:
        from daily_draw.models import DrawItem, DrawRecord

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            Image.new("RGB", (252, 252), "#ff99aa").save(root / "portrait.png")
            item = DrawItem("test", "测试使徒", "portrait.png")
            record = DrawRecord(
                DrawIdentity("qq_official", "member"),
                "2026-09-15",
                (item,),
                "2026-09-15T12:00:00+08:00",
            )
            rendered = DailyDrawCardRenderer(root).render(record)
            with Image.open(__import__("io").BytesIO(rendered)) as image:
                self.assertEqual(image.size, (720, 820))
                self.assertEqual(image.format, "PNG")

    def test_single_pull_portrait_scales_up_to_the_card_frame(self) -> None:
        from daily_draw.models import DrawItem, DrawRecord

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            Image.new("RGB", (126, 126), "#ff99aa").save(root / "portrait.png")
            renderer = DailyDrawCardRenderer(root)
            portrait = renderer._load_portrait("portrait.png", size=470)
            item = DrawItem("test", "测试使徒", "portrait.png")
            record = DrawRecord(
                DrawIdentity("qq_official", "member"),
                "2026-09-15",
                (item,),
                "2026-09-15T12:00:00+08:00",
            )
            first = renderer.render(record, already_drawn=False)
            replay = renderer.render(record, already_drawn=True)

        # A 126 px source portrait is enlarged to nearly fill its 470 px frame,
        # but retains an intentional edge margin rather than being cropped.
        self.assertEqual(portrait.getpixel((56, 235)), (255, 153, 170))
        self.assertEqual(portrait.getpixel((40, 235)), (233, 238, 243))
        with Image.open(__import__("io").BytesIO(first)) as first_image:
            self.assertIn((242, 138, 61), first_image.get_flattened_data())
        with Image.open(__import__("io").BytesIO(replay)) as replay_image:
            self.assertIn((128, 104, 216), replay_image.get_flattened_data())

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

    async def test_second_single_pull_returns_first_record(self) -> None:
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
        self.assertEqual(first.updates[0].copies, 1)
        self.assertEqual(first.updates[0].current_stars, 1)
        self.assertEqual(collection.unlocked_count, 1)
        self.assertEqual(collection.entries[0].copies, 1)

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
        self.assertEqual(collection.entries[0].copies, 1)

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
        self.assertEqual(parse_draw_command("/每日单抽"), "draw")
        self.assertEqual(parse_draw_command("每日单抽"), "draw")
        self.assertIsNone(parse_draw_command("/每日抽取"))
        self.assertIsNone(parse_draw_command("/进行十连"))
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
                    "content": "/每日单抽",
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

    async def test_single_pull_sends_only_the_result_card(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            repository = DrawRepository(root / "draw.sqlite3")
            await repository.initialize()
            service = DailyDrawService(
                write_pool(root / "pool.json"), repository, DrawEngine(FakeRandom())
            )
            menus = SimpleNamespace(
                send_image=AsyncMock(),
                send_daily_draw_view=AsyncMock(),
            )
            controller = DailyDrawController(
                service,
                menus,
                renderer=SimpleNamespace(
                    render=lambda record, *, already_drawn=False: b"single-card"
                ),
            )
            context = SimpleNamespace(
                content="/每日单抽",
                platform="qq_official",
                user_id="member",
                group_id="group",
                scene_type="group",
                message_id="message",
            )

            handled = await controller.handle_text(context)

        self.assertTrue(handled)
        menus.send_image.assert_awaited_once_with(
            "group",
            "group",
            b"single-card",
            reply_to="message",
            keyboard=build_daily_draw_keyboard(),
        )
        menus.send_daily_draw_view.assert_not_awaited()

    async def test_already_drawn_result_marks_card_as_replay(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            repository = DrawRepository(root / "draw.sqlite3")
            await repository.initialize()
            service = DailyDrawService(
                write_pool(root / "pool.json"), repository, DrawEngine(FakeRandom())
            )
            identity = DrawIdentity("qq_official", "member")
            await service.draw(identity)
            menus = SimpleNamespace(send_image=AsyncMock(), send_daily_draw_view=AsyncMock())
            render = Mock()

            def render_card(record, *, already_drawn=False):
                render(already_drawn=already_drawn)
                return b"replayed-card"

            controller = DailyDrawController(
                service,
                menus,
                renderer=SimpleNamespace(render=render_card),
            )
            context = SimpleNamespace(
                content="/每日单抽",
                platform="qq_official",
                user_id="member",
                group_id="group",
                scene_type="group",
                message_id="message-2",
            )
            await controller.handle_text(context)

        render.assert_called_once_with(already_drawn=True)
        menus.send_image.assert_awaited_once_with(
            "group",
            "group",
            b"replayed-card",
            reply_to="message-2",
            keyboard=build_daily_draw_keyboard(),
        )


if __name__ == "__main__":
    unittest.main()
