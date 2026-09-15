from __future__ import annotations

import random
from typing import Protocol, TypeVar

from .catalog import DrawCatalog
from .models import DrawItem


T = TypeVar("T")


class RandomSource(Protocol):
    def choice(self, sequence: tuple[T, ...]) -> T: ...


class DrawEngine:
    """Ten independent selections from one uniformly weighted pool."""

    def __init__(self, rng: RandomSource | None = None) -> None:
        self._rng = rng or random.SystemRandom()

    def draw_ten(self, catalog: DrawCatalog) -> tuple[DrawItem, ...]:
        if not catalog.ready:
            raise ValueError("抽取名单尚未完整配置")
        pool = catalog.items()
        return tuple(self._rng.choice(pool) for _ in range(10))
