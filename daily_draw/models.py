from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DrawIdentity:
    platform: str
    user_id: str
    group_id: str = ""


@dataclass(frozen=True, slots=True)
class DrawItem:
    item_id: str
    name: str
    rarity: int


@dataclass(frozen=True, slots=True)
class DrawRecord:
    identity: DrawIdentity
    draw_date: str
    items: tuple[DrawItem, ...]
    created_at: str

