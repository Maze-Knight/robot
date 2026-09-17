from __future__ import annotations

# LEGACY LOCAL IMPLEMENTATION: loaded only when TRICKCAL_MODE=local.

from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

from .catalog import Catalog, CatalogService, validate_soshage_export
from .models import BoardProfile, PlatformIdentity
from .repository import TrickcalRepository


class TrickcalBoardService:
    def __init__(self, repository: TrickcalRepository, catalog: CatalogService, *, public_url: str, ticket_minutes: int, session_days: int) -> None:
        self.repository = repository
        self.catalog = catalog
        self.public_url = self._validate_public_url(public_url)
        self.ticket_minutes = ticket_minutes
        self.session_days = session_days

    @staticmethod
    def _validate_public_url(value: str) -> str:
        parsed = urlsplit(value.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("TRICKCAL_WEB_PUBLIC_URL 必须是完整的 /tr-board/ 地址。")
        if parsed.scheme == "http" and (parsed.hostname or "").lower() not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("公网蜡笔板必须使用 HTTPS。")
        path = parsed.path.rstrip("/")
        if path != "/tr-board":
            raise ValueError("TRICKCAL_WEB_PUBLIC_URL 必须以 /tr-board/ 结尾。")
        return urlunsplit((parsed.scheme, parsed.netloc, "/tr-board/", "", ""))

    async def identity(self, platform_user_id: str) -> PlatformIdentity:
        return await self.repository.touch_identity("qq_official", platform_user_id)

    async def issue_entry(self, platform_user_id: str) -> str:
        identity = await self.identity(platform_user_id)
        ticket = await self.repository.issue_ticket(identity, self.ticket_minutes)
        return self.public_url + "entry?t=" + quote(ticket, safe="")

    async def redeem_entry(self, ticket: str) -> tuple[str, str] | None:
        return await self.repository.redeem_ticket(ticket, self.session_days)

    async def profile_for_user(self, platform_user_id: str) -> BoardProfile | None:
        identity = await self.identity(platform_user_id)
        return await self.repository.profile_for_identity(identity.id)

    async def state(self, profile_id: int) -> dict[str, Any]:
        catalog = await self.catalog.get()
        data = await self.repository.board_data(profile_id)
        return {"catalog": catalog.public(), "board": {key: sorted(value) for key, value in data.items()}}

    async def set_owned(self, profile_id: int, unit_id: int, owned: bool) -> None:
        catalog = await self.catalog.get()
        if unit_id not in catalog.units:
            raise ValueError("角色目录中没有这个项目。")
        await self.repository.set_unit(profile_id, unit_id, owned)

    async def own_all(self, profile_id: int) -> None:
        catalog = await self.catalog.get()
        await self.repository.set_all_units(profile_id, list(catalog.units))

    async def set_node(self, profile_id: int, node_id: int, state: str | None) -> None:
        catalog = await self.catalog.get()
        if node_id not in catalog.nodes:
            raise ValueError("节点目录中没有这个项目。")
        if state not in {None, "selected", "planned"}:
            raise ValueError("节点状态不正确。")
        await self.repository.set_node(profile_id, node_id, state)

    async def import_export(self, profile_id: int, raw: str) -> None:
        units, selected, planned = validate_soshage_export(raw)
        catalog = await self.catalog.get()
        known_units = [item for item in units if item in catalog.units]
        known_selected = [item for item in selected if item in catalog.nodes]
        known_planned = [item for item in planned if item in catalog.nodes and item not in set(known_selected)]
        await self.repository.replace_board(profile_id, known_units, known_selected, known_planned)

    async def export(self, profile_id: int) -> dict[str, Any]:
        data = await self.repository.board_data(profile_id)
        board_by_unit: dict[int, dict[str, list[int]]] = {}
        catalog = await self.catalog.get()
        for node_id in data["selected"]:
            node = catalog.nodes.get(node_id)
            if node:
                board_by_unit.setdefault(int(node["unit_id"]), {"selectedNodes": [], "plannedNodes": []})["selectedNodes"].append(node_id)
        for node_id in data["planned"]:
            node = catalog.nodes.get(node_id)
            if node:
                board_by_unit.setdefault(int(node["unit_id"]), {"selectedNodes": [], "plannedNodes": []})["plannedNodes"].append(node_id)
        return {"version": 1, "units": [[item, 1] for item in sorted(data["units"])], "cards": [], "pets": [], "boards": [[unit, values] for unit, values in sorted(board_by_unit.items())], "filter": [], "stepFilter": [], "statFilter": [], "purpleWeight": 8, "goldWeight": 1000}

    async def get_summary(self, identity_id: int) -> dict[str, int] | None:
        profile = await self.repository.profile_for_identity(identity_id)
        if profile is None:
            return None
        catalog = await self.catalog.get()
        data = await self.repository.board_data(profile.id)
        owned = data["units"]
        total_nodes = [node_id for unit_id in owned for node_id in catalog.by_unit.get(unit_id, ())]
        selected = data["selected"] & set(total_nodes)
        planned = data["planned"] & set(total_nodes)
        remaining = set(total_nodes) - selected
        return {"owned_units": len(owned), "total_units": len(catalog.units), "selected_nodes": len(selected), "total_nodes": len(total_nodes), "planned_nodes": len(planned), "remaining_gold": sum(int(catalog.nodes[node_id].get("gold") or 0) for node_id in remaining), "remaining_gold_crayons": sum(int(catalog.nodes[node_id].get("gold_crayons") or 0) for node_id in remaining)}
