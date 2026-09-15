from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import DrawItem


class DrawCatalogError(ValueError):
    pass


class DrawCatalog:
    """Load the user-maintained draw pool without inventing any entries."""

    _KEYS = {1: "one_star", 2: "two_star", 3: "three_star"}

    def __init__(self, pools: dict[int, tuple[DrawItem, ...]]) -> None:
        self._pools = pools

    @classmethod
    def load(cls, path: Path) -> DrawCatalog:
        if not path.is_file():
            return cls({rarity: () for rarity in cls._KEYS})
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DrawCatalogError(f"奖池文件无法读取：{exc}") from exc
        if not isinstance(raw, dict):
            raise DrawCatalogError("奖池文件顶层必须是 JSON 对象")

        pools: dict[int, tuple[DrawItem, ...]] = {}
        seen_ids: set[str] = set()
        for rarity, key in cls._KEYS.items():
            entries = raw.get(key, [])
            if not isinstance(entries, list):
                raise DrawCatalogError(f"{key} 必须是列表")
            items: list[DrawItem] = []
            for index, entry in enumerate(entries, start=1):
                item = cls._parse_item(entry, rarity, key, index)
                if item.item_id in seen_ids:
                    raise DrawCatalogError(f"奖池项目 id 重复：{item.item_id}")
                seen_ids.add(item.item_id)
                items.append(item)
            pools[rarity] = tuple(items)
        return cls(pools)

    @staticmethod
    def _parse_item(entry: Any, rarity: int, key: str, index: int) -> DrawItem:
        if isinstance(entry, str):
            name = entry.strip()
            item_id = f"{key}-{index}"
        elif isinstance(entry, dict):
            name = str(entry.get("name", "")).strip()
            item_id = str(entry.get("id", f"{key}-{index}")).strip()
        else:
            raise DrawCatalogError(f"{key} 第 {index} 项必须是文字或对象")
        if not name:
            raise DrawCatalogError(f"{key} 第 {index} 项缺少 name")
        if not item_id:
            raise DrawCatalogError(f"{key} 第 {index} 项缺少 id")
        return DrawItem(item_id=item_id, name=name, rarity=rarity)

    @property
    def ready(self) -> bool:
        return all(self._pools.get(rarity) for rarity in (1, 2, 3))

    def items(self, rarity: int) -> tuple[DrawItem, ...]:
        return self._pools.get(rarity, ())

