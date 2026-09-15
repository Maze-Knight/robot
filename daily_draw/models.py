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
    image: str = ""


@dataclass(frozen=True, slots=True)
class DrawRecord:
    identity: DrawIdentity
    draw_date: str
    items: tuple[DrawItem, ...]
    created_at: str


@dataclass(frozen=True, slots=True)
class CollectionEntry:
    item: DrawItem
    copies: int = 0

    @property
    def unlocked(self) -> bool:
        return self.copies > 0

    @property
    def current_stars(self) -> int:
        return self.copies


@dataclass(frozen=True, slots=True)
class CollectionSnapshot:
    identity: DrawIdentity
    entries: tuple[CollectionEntry, ...]

    @property
    def unlocked_count(self) -> int:
        return sum(entry.unlocked for entry in self.entries)

    @property
    def total_count(self) -> int:
        return len(self.entries)

    @property
    def completion_percent(self) -> float:
        return self.unlocked_count / self.total_count * 100 if self.total_count else 0.0


@dataclass(frozen=True, slots=True)
class CollectionUpdate:
    item: DrawItem
    previous_copies: int
    copies: int

    @property
    def is_new(self) -> bool:
        return self.previous_copies == 0

    @property
    def current_stars(self) -> int:
        return self.copies
