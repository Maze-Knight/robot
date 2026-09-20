from __future__ import annotations

import random
from typing import Protocol, TypeVar

from .catalog import DrawCatalog
from .models import DrawItem


T = TypeVar("T")


class RandomSource(Protocol):
    def choice(self, sequence: tuple[T, ...]) -> T: ...


class DrawEngine:
    """One uniformly weighted daily selection from the configured pool."""

    def __init__(self, rng: RandomSource | None = None) -> None:
        self._rng = rng or random.SystemRandom()

    def draw_one(self, catalog: DrawCatalog) -> DrawItem:
        if not catalog.ready:
            raise ValueError("抽取名单尚未完整配置")
        pool = catalog.items()
        return self._rng.choice(pool)
