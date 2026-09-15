from __future__ import annotations

import random
from typing import Protocol, TypeVar

from .catalog import DrawCatalog
from .models import DrawItem


T = TypeVar("T")


class RandomSource(Protocol):
    def randrange(self, stop: int) -> int: ...
    def choice(self, sequence: tuple[T, ...]) -> T: ...


class DrawEngine:
    """Official rarity odds with a ★★-or-higher ten-pull guarantee."""

    def __init__(self, rng: RandomSource | None = None) -> None:
        self._rng = rng or random.SystemRandom()

    def _roll_rarity(self) -> int:
        roll = self._rng.randrange(10_000)
        if roll < 300:
            return 3
        if roll < 2_400:
            return 2
        return 1

    def _roll_guaranteed_rarity(self) -> int:
        # Keep the relative 3% : 21% weights when the guarantee is activated.
        return 3 if self._rng.randrange(2_400) < 300 else 2

    def draw_ten(self, catalog: DrawCatalog) -> tuple[DrawItem, ...]:
        if not catalog.ready:
            raise ValueError("抽取名单尚未完整配置")
        rarities = [self._roll_rarity() for _ in range(10)]
        if all(rarity == 1 for rarity in rarities):
            rarities[-1] = self._roll_guaranteed_rarity()
        return tuple(self._rng.choice(catalog.items(rarity)) for rarity in rarities)

