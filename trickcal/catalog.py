from __future__ import annotations

# LEGACY LOCAL IMPLEMENTATION: loaded only when TRICKCAL_MODE=local.

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any

import httpx

from .repository import TrickcalRepository


SOSHAGE_API = "https://soshage.com/ztrickapi/zh-tw"
MAX_CATALOG_BYTES = 4 * 1024 * 1024
CATALOG_TTL_SECONDS = 24 * 60 * 60
PERCENT_STAT_TYPES = frozenset({88, 89, 92, 93, 95, 97, 99, 101, 103})
GOLD_CRAYON_ITEM_ID = 610004


class CatalogError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class Catalog:
    units: dict[int, dict[str, Any]]
    nodes: dict[int, dict[str, Any]]
    by_unit: dict[int, tuple[int, ...]]
    fetched_at: float
    source_label: str
    stale: bool = False

    def public(self) -> dict[str, Any]:
        return {
            "units": [{"id": uid, **value} for uid, value in self.units.items()],
            "nodes": [{"id": uid, **value} for uid, value in self.nodes.items()],
            "updated_at": self.fetched_at,
            "source": self.source_label,
            "stale": self.stale,
        }


def _positive(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 0 < value <= 2**53 - 1


def _gold_crayons(row: dict[str, Any]) -> int:
    ids = str(row.get("need_item_ids") or "").split(",")
    amounts = str(row.get("need_item_values") or "").split(",")
    total = 0
    for index, raw_id in enumerate(ids):
        try:
            if int(raw_id.strip()) == GOLD_CRAYON_ITEM_ID:
                total += max(0, int(float(amounts[index].strip())))
        except (ValueError, IndexError):
            continue
    return total


def parse_catalog(units_payload: Any, nodes_payload: Any) -> Catalog:
    if not isinstance(units_payload, list) or len(units_payload) > 2_000:
        raise CatalogError("Soshage 角色目录格式不正确。")
    if not isinstance(nodes_payload, list) or len(nodes_payload) > 100_000:
        raise CatalogError("Soshage 节点目录格式不正确。")
    units: dict[int, dict[str, Any]] = {}
    for row in units_payload:
        if not isinstance(row, dict) or not _positive(row.get("uid")):
            continue
        uid = int(row["uid"])
        units[uid] = {
            "name": str(row.get("name") or "").strip()[:60],
            "alias": str(row.get("resource_name") or row.get("icon") or "").strip()[:60],
            "personality": row.get("personality") if type(row.get("personality")) is int else -1,
        }
    nodes: dict[int, dict[str, Any]] = {}
    grouped: dict[int, list[int]] = {}
    for row in nodes_payload:
        if not isinstance(row, dict):
            continue
        uid, unit_id, layer = row.get("uid"), row.get("unit_uid"), row.get("step")
        if not all(_positive(value) for value in (uid, unit_id, layer)):
            continue
        if int(unit_id) not in units:
            continue
        node = {
            "unit_id": int(unit_id),
            "layer": int(layer),
            "node_type": int(row.get("node_type") or 0),
            "stat_type": str(row.get("stat_type") or ""),
            "stat_value": str(row.get("stat_value") or ""),
            "gold": max(0, int(row.get("need_gold") or 0)),
            "gold_crayons": _gold_crayons(row),
        }
        nodes[int(uid)] = node
        grouped.setdefault(int(unit_id), []).append(int(uid))
    if not units or not nodes:
        raise CatalogError("Soshage 公开目录为空。")
    return Catalog(units, nodes, {key: tuple(value) for key, value in grouped.items()}, time.time(), "Soshage")


def catalog_from_payload(payload: Any, *, fetched_at: float, source_label: str, stale: bool = False) -> Catalog | None:
    if not isinstance(payload, dict):
        return None
    units_value, nodes_value = payload.get("units"), payload.get("nodes")
    if not isinstance(units_value, list) or not isinstance(nodes_value, list):
        return None
    units: dict[int, dict[str, Any]] = {}
    nodes: dict[int, dict[str, Any]] = {}
    grouped: dict[int, list[int]] = {}
    for row in units_value:
        if not isinstance(row, dict) or not _positive(row.get("id")):
            return None
        units[int(row["id"])] = {"name": str(row.get("name") or "")[:60], "alias": str(row.get("alias") or "")[:60], "personality": int(row.get("personality", -1))}
    for row in nodes_value:
        if not isinstance(row, dict) or not _positive(row.get("id")) or not _positive(row.get("unit_id")):
            return None
        uid = int(row["id"])
        nodes[uid] = {key: row.get(key) for key in ("unit_id", "layer", "node_type", "stat_type", "stat_value", "gold", "gold_crayons")}
        grouped.setdefault(int(row["unit_id"]), []).append(uid)
    if not units or not nodes:
        return None
    return Catalog(units, nodes, {key: tuple(value) for key, value in grouped.items()}, fetched_at, source_label, stale)


class CatalogService:
    """Bounded remote catalogue refresh with a durable last-known-good cache."""

    def __init__(self, repository: TrickcalRepository, client: httpx.AsyncClient) -> None:
        self._repository = repository
        self._client = client
        self._catalog: Catalog | None = None
        self._lock = asyncio.Lock()

    async def get(self, *, refresh: bool = False) -> Catalog:
        async with self._lock:
            if self._catalog is not None and not refresh and time.time() - self._catalog.fetched_at < CATALOG_TTL_SECONDS:
                return self._catalog
            cached = await self._repository.get_cached_catalog()
            cached_catalog = None if cached is None else catalog_from_payload(cached["payload"], fetched_at=cached["fetched_at"], source_label=cached["source_label"])
            if cached_catalog is not None and not refresh and time.time() - cached_catalog.fetched_at < CATALOG_TTL_SECONDS:
                self._catalog = cached_catalog
                return cached_catalog
            try:
                units_response, nodes_response = await asyncio.gather(
                    self._get_json("/unit", 1 * 1024 * 1024),
                    self._get_json("/unit/board", MAX_CATALOG_BYTES),
                )
                fresh = parse_catalog(units_response, nodes_response)
                await self._repository.save_catalog(fresh.public(), fresh.source_label)
                self._catalog = fresh
                return fresh
            except CatalogError:
                if cached_catalog is None:
                    raise
                self._catalog = Catalog(cached_catalog.units, cached_catalog.nodes, cached_catalog.by_unit, cached_catalog.fetched_at, cached_catalog.source_label, True)
                return self._catalog

    async def _get_json(self, path: str, maximum: int) -> Any:
        try:
            async with self._client.stream("GET", SOSHAGE_API + path, headers={"Accept": "application/json", "Accept-Language": "zh-TW"}) as response:
                if response.status_code != 200 or "json" not in response.headers.get("content-type", "").lower():
                    raise CatalogError("Soshage 蜡笔板目录暂时不可用。")
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > maximum:
                        raise CatalogError("Soshage 蜡笔板目录响应过大。")
        except httpx.HTTPError as exc:
            raise CatalogError("Soshage 蜡笔板目录网络异常。") from exc
        try:
            return json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CatalogError("Soshage 蜡笔板目录格式无法识别。") from exc

    async def refresh_worker(self) -> None:
        """Refresh once per day without ever discarding last-known-good data."""
        while True:
            try:
                await self.get(refresh=True)
            except CatalogError:
                # The next scheduled attempt may recover; cached data remains intact.
                pass
            await asyncio.sleep(CATALOG_TTL_SECONDS)


def validate_soshage_export(raw: str) -> tuple[list[int], list[int], list[int]]:
    if len(raw.encode("utf-8")) > 512 * 1024:
        raise ValueError("导入文件不能超过 512 KiB。")
    try:
        value = json.loads(raw)
    except (TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("无法识别这份 JSON；请使用 Soshage 收藏页的导出文件。") from exc
    required = {
        "version", "units", "cards", "pets", "boards", "filter", "stepFilter",
        "statFilter", "purpleWeight", "goldWeight",
    }
    if not isinstance(value, dict) or set(value) != required or value.get("version") != 1:
        raise ValueError("不支持这份导出格式；目前仅兼容 Soshage collection v1。")

    def pairs(name: str) -> list[int]:
        rows = value.get(name, [])
        if not isinstance(rows, list) or len(rows) > 10_000:
            raise ValueError("导入文件中的收藏字段不正确。")
        result: list[int] = []
        for row in rows:
            if not isinstance(row, list) or len(row) != 2 or not _positive(row[0]) or not _positive(row[1]):
                raise ValueError("导入文件中的收藏字段不正确。")
            result.append(int(row[0]))
        return list(dict.fromkeys(result))

    units = pairs("units")
    pairs("cards")
    for key in ("pets", "filter", "stepFilter"):
        rows = value[key]
        if not isinstance(rows, list) or len(rows) > 10_000 or any(not _positive(item) for item in rows):
            raise ValueError("导入文件中的收藏字段不正确。")
    if (
        not isinstance(value["statFilter"], list)
        or len(value["statFilter"]) > 10_000
        or any(not isinstance(item, str) or len(item.encode("utf-8")) > 255 for item in value["statFilter"])
        or not _positive(value["purpleWeight"])
        or not _positive(value["goldWeight"])
    ):
        raise ValueError("导入文件中的筛选或权重字段不正确。")
    selected: list[int] = []
    planned: list[int] = []
    boards = value.get("boards", [])
    if not isinstance(boards, list) or len(boards) > 10_000:
        raise ValueError("导入文件中的蜡笔板字段不正确。")
    for row in boards:
        if not isinstance(row, list) or len(row) != 2 or not _positive(row[0]) or not isinstance(row[1], dict):
            raise ValueError("导入文件中的蜡笔板字段不正确。")
        for target, key in ((selected, "selectedNodes"), (planned, "plannedNodes")):
            values = row[1].get(key, [])
            if not isinstance(values, list) or any(not _positive(item) for item in values):
                raise ValueError("导入文件中的节点字段不正确。")
            target.extend(int(item) for item in values)
    selected = list(dict.fromkeys(selected))
    if set(selected) & set(planned):
        raise ValueError("节点不能同时属于已点亮和计划。")
    planned = list(dict.fromkeys(planned))
    return units, selected, planned
