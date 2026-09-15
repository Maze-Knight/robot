from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import DrawItem


class DrawCatalogError(ValueError):
    pass


class DrawCatalog:
    """Load one equally weighted apostle pool."""

    def __init__(self, items: tuple[DrawItem, ...], pool_id: str = "") -> None:
        self._items = items
        self.pool_id = pool_id

    @classmethod
    def load(cls, path: Path) -> DrawCatalog:
        if not path.is_file():
            return cls(())
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DrawCatalogError(f"奖池文件无法读取：{exc}") from exc
        if not isinstance(raw, dict):
            raise DrawCatalogError("奖池文件顶层必须是 JSON 对象")

        pool_id = str(raw.get("pool_id", "")).strip()
        entries = raw.get("items", [])
        if not pool_id:
            raise DrawCatalogError("奖池文件缺少 pool_id")
        if not isinstance(entries, list):
            raise DrawCatalogError("items 必须是列表")

        items: list[DrawItem] = []
        seen_ids: set[str] = set()
        for index, entry in enumerate(entries, start=1):
            item = cls._parse_item(entry, index)
            if item.item_id in seen_ids:
                raise DrawCatalogError(f"奖池项目 id 重复：{item.item_id}")
            seen_ids.add(item.item_id)
            items.append(item)
        return cls(tuple(items), pool_id)

    @staticmethod
    def _parse_item(entry: Any, index: int) -> DrawItem:
        if not isinstance(entry, dict):
            raise DrawCatalogError(f"items 第 {index} 项必须是对象")
        name = str(entry.get("name", "")).strip()
        item_id = str(entry.get("id", "")).strip()
        image = str(entry.get("image", "")).strip()
        if not name:
            raise DrawCatalogError(f"items 第 {index} 项缺少 name")
        if not item_id:
            raise DrawCatalogError(f"items 第 {index} 项缺少 id")
        if not image:
            raise DrawCatalogError(f"items 第 {index} 项缺少 image")
        return DrawItem(item_id=item_id, name=name, image=image)

    @property
    def ready(self) -> bool:
        return bool(self.pool_id and self._items)

    def items(self) -> tuple[DrawItem, ...]:
        return self._items

    def all_items(self) -> tuple[DrawItem, ...]:
        return self._items
