from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

import httpx

from trickcal.catalog import Catalog
from trickcal.commands import TrickcalController
from trickcal.repository import TrickcalRepository
from trickcal.service import TrickcalBoardService
from trickcal.web import BoardWeb


class StaticCatalog:
    def __init__(self) -> None:
        self.value = Catalog(
            units={1: {"name": "艾琳娜", "alias": "elena", "personality": 0}, 2: {"name": "露皮", "alias": "lupi", "personality": 1}},
            nodes={11: {"unit_id": 1, "layer": 1, "node_type": 3, "stat_type": "88", "stat_value": "10", "gold": 100, "gold_crayons": 1}, 12: {"unit_id": 1, "layer": 2, "node_type": 3, "stat_type": "89", "stat_value": "20", "gold": 200, "gold_crayons": 2}, 21: {"unit_id": 2, "layer": 3, "node_type": 3, "stat_type": "95", "stat_value": "30", "gold": 300, "gold_crayons": 3}},
            by_unit={1: (11, 12), 2: (21,)}, fetched_at=1.0, source_label="test",
        )

    async def get(self, *, refresh: bool = False) -> Catalog:
        return self.value


class Menus:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple, dict]] = []

    async def send_trickcal_home(self, *args, **kwargs):
        self.calls.append(("home", args, kwargs))

    async def send_trickcal_login(self, *args, **kwargs):
        self.calls.append(("login", args, kwargs))

    async def send_services_menu(self, *args, **kwargs):
        self.calls.append(("services", args, kwargs))

    async def send_plain_text(self, *args, **kwargs):
        self.calls.append(("text", args, kwargs))


class TrickcalTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.repository = TrickcalRepository(Path(self.temp.name) / "board.sqlite3")
        await self.repository.initialize()
        self.catalog = StaticCatalog()
        self.service = TrickcalBoardService(self.repository, self.catalog, public_url="http://127.0.0.1:8080/tr-board/", ticket_minutes=10, session_days=30)

    async def asyncTearDown(self) -> None:
        self.temp.cleanup()

    async def _profile(self, user: str = "c2c-openid") -> int:
        url = await self.service.issue_entry(user)
        result = await self.service.redeem_entry(url.rsplit("=", 1)[1])
        assert result is not None
        profile = await self.service.profile_for_user(user)
        assert profile is not None
        return profile.id

    async def test_c2c_identity_is_created(self) -> None:
        identity = await self.service.identity("c2c-openid")
        self.assertEqual(identity.platform, "qq_official")
        self.assertEqual(identity.platform_user_id, "c2c-openid")

    async def test_group_identity_is_not_guessed_as_c2c(self) -> None:
        c2c = await self.service.identity("c2c-openid")
        group = await self.service.identity("member-openid")
        self.assertNotEqual(c2c.id, group.id)

    async def test_profile_is_created_on_ticket_redemption(self) -> None:
        url = await self.service.issue_entry("first-user")
        self.assertIsNone(await self.service.profile_for_user("first-user"))
        self.assertIsNotNone(await self.service.redeem_entry(url.rsplit("=", 1)[1]))
        self.assertIsNotNone(await self.service.profile_for_user("first-user"))

    async def test_ticket_is_one_time(self) -> None:
        url = await self.service.issue_entry("one-time")
        token = url.rsplit("=", 1)[1]
        self.assertIsNotNone(await self.service.redeem_entry(token))
        self.assertIsNone(await self.service.redeem_entry(token))

    async def test_expired_ticket_is_rejected(self) -> None:
        url = await self.service.issue_entry("expired")
        with closing(self.repository._connect()) as db, db:
            db.execute("UPDATE web_login_ticket SET expires_at=0")
        self.assertIsNone(await self.service.redeem_entry(url.rsplit("=", 1)[1]))

    async def test_ticket_database_never_contains_plain_value(self) -> None:
        url = await self.service.issue_entry("hash-ticket")
        token = url.rsplit("=", 1)[1]
        with closing(self.repository._connect()) as db:
            value = str(db.execute("SELECT ticket_hash FROM web_login_ticket").fetchone()[0])
        self.assertNotEqual(value, token)
        self.assertEqual(len(value), 64)

    async def test_session_is_created_and_validated(self) -> None:
        url = await self.service.issue_entry("session")
        redeemed = await self.service.redeem_entry(url.rsplit("=", 1)[1])
        assert redeemed is not None
        session, csrf = redeemed
        current = await self.repository.get_session(session)
        self.assertEqual(current["csrf_token"], csrf)

    async def test_session_database_never_contains_plain_value(self) -> None:
        url = await self.service.issue_entry("session-hash")
        session, _ = (await self.service.redeem_entry(url.rsplit("=", 1)[1]))
        with closing(self.repository._connect()) as db:
            stored = str(db.execute("SELECT token_hash FROM web_session").fetchone()[0])
        self.assertNotEqual(stored, session)
        self.assertEqual(len(stored), 64)

    async def test_node_light_and_revoke(self) -> None:
        profile = await self._profile()
        await self.service.set_node(profile, 11, "selected")
        self.assertIn(11, (await self.repository.board_data(profile))["selected"])
        await self.service.set_node(profile, 11, None)
        self.assertNotIn(11, (await self.repository.board_data(profile))["selected"])

    async def test_planned_node(self) -> None:
        profile = await self._profile()
        await self.service.set_node(profile, 12, "planned")
        self.assertIn(12, (await self.repository.board_data(profile))["planned"])

    async def test_owned_state(self) -> None:
        profile = await self._profile()
        await self.service.set_owned(profile, 1, True)
        self.assertIn(1, (await self.repository.board_data(profile))["units"])
        await self.service.set_owned(profile, 1, False)
        self.assertNotIn(1, (await self.repository.board_data(profile))["units"])

    async def test_bulk_owned_state(self) -> None:
        profile = await self._profile()
        await self.service.own_all(profile)
        self.assertEqual((await self.repository.board_data(profile))["units"], {1, 2})

    async def test_summary_and_resources(self) -> None:
        profile = await self._profile("summary")
        await self.service.set_owned(profile, 1, True)
        await self.service.set_node(profile, 11, "selected")
        identity = await self.service.identity("summary")
        summary = await self.service.get_summary(identity.id)
        assert summary is not None
        self.assertEqual(summary["selected_nodes"], 1)
        self.assertEqual(summary["remaining_gold"], 200)
        self.assertEqual(summary["remaining_gold_crayons"], 2)

    async def test_soshage_json_import_and_export(self) -> None:
        profile = await self._profile("import")
        raw = json.dumps({"version": 1, "units": [[1, 1]], "cards": [], "pets": [], "boards": [[1, {"selectedNodes": [11], "plannedNodes": [12]}]], "filter": [], "stepFilter": [], "statFilter": [], "purpleWeight": 8, "goldWeight": 1000})
        await self.service.import_export(profile, raw)
        exported = await self.service.export(profile)
        self.assertEqual(exported["units"], [[1, 1]])
        self.assertEqual(exported["boards"][0][1]["selectedNodes"], [11])

    async def test_invalid_json_import_is_rejected(self) -> None:
        profile = await self._profile("bad-import")
        with self.assertRaises(ValueError):
            await self.service.import_export(profile, "not json")

    async def test_unauthenticated_api_is_rejected(self) -> None:
        web = BoardWeb(self.service, secure_cookie=False)
        transport = httpx.ASGITransport(app=web.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8080") as client:
            response = await client.get("/tr-board/api/state")
        self.assertEqual(response.status_code, 401)

    async def test_csrf_and_same_origin_are_required(self) -> None:
        web = BoardWeb(self.service, secure_cookie=False)
        transport = httpx.ASGITransport(app=web.app)
        url = await self.service.issue_entry("csrf")
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8080", follow_redirects=False) as client:
            entry = await client.get(url)
            self.assertEqual(entry.status_code, 302)
            csrf = (await client.get("/tr-board/api/session")).json()["csrf"]
            denied = await client.put("/tr-board/api/units/1", json={"owned": True})
            self.assertEqual(denied.status_code, 403)
            allowed = await client.put("/tr-board/api/units/1", json={"owned": True}, headers={"Origin": "http://127.0.0.1:8080", "X-CSRF-Token": csrf})
        self.assertEqual(allowed.status_code, 200)

    async def test_ticket_entry_sets_httponly_session_cookie(self) -> None:
        web = BoardWeb(self.service, secure_cookie=False)
        transport = httpx.ASGITransport(app=web.app)
        url = await self.service.issue_entry("cookie")
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8080", follow_redirects=False) as client:
            response = await client.get(url)
        self.assertIn("HttpOnly", response.headers["set-cookie"])
        self.assertIn("SameSite=lax", response.headers["set-cookie"])

    async def test_public_catalog_needs_no_login(self) -> None:
        web = BoardWeb(self.service, secure_cookie=False)
        transport = httpx.ASGITransport(app=web.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8080") as client:
            response = await client.get("/api/v1/tr-board/catalog")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["source"], "test")

    async def test_controller_progress_for_new_user_offers_entry(self) -> None:
        menus = Menus(); controller = TrickcalController(self.service, menus)
        await controller.handle_interaction("group", "group-openid", "member-openid", "trickcal:progress", "event")
        self.assertEqual(menus.calls[0][0], "login")

    async def test_controller_open_generates_login_link(self) -> None:
        menus = Menus(); controller = TrickcalController(self.service, menus)
        await controller.handle_interaction("c2c", "openid", "openid", "trickcal:open", "event")
        self.assertEqual(menus.calls[0][0], "login")
        self.assertIn("/tr-board/entry?t=", menus.calls[0][1][3])
