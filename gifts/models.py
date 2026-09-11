from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


@dataclass(frozen=True, slots=True)
class GiftPeriod:
    id: str
    name: str
    code: str
    folder_type: str
    sort_order: int
    created_at: str

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> "GiftPeriod":
        return cls(
            id=str(raw.get("id", "")),
            name=str(raw.get("name", "未命名期次")).strip() or "未命名期次",
            code=str(raw.get("code", "")),
            folder_type=str(raw.get("folder_type", "")),
            sort_order=int(_number(raw.get("sort_order"))),
            created_at=str(raw.get("created_at", "")),
        )

    @property
    def created_timestamp(self) -> float:
        try:
            return datetime.fromisoformat(self.created_at.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return 0.0


@dataclass(frozen=True, slots=True)
class Gift:
    id: str
    name: str
    price: float
    total_value: float
    ratio: float
    rating_code: str
    status: str
    show_in_ranking: bool
    is_tier: bool
    tier_index: int | None
    tier_total: int | None
    special_type: str

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> "Gift":
        tier_index = raw.get("tier_index")
        tier_total = raw.get("tier_total")
        return cls(
            id=str(raw.get("id", "")),
            name=str(raw.get("name", "未命名礼包")).strip() or "未命名礼包",
            price=_number(raw.get("price")),
            total_value=_number(raw.get("total_crystal_value")),
            ratio=_number(raw.get("cost_performance")),
            rating_code=str(raw.get("rating", "")),
            status=str(raw.get("status", "")),
            show_in_ranking=bool(raw.get("show_in_ranking", True)),
            is_tier=bool(raw.get("is_tier_gift", False)),
            tier_index=int(_number(tier_index)) if tier_index is not None else None,
            tier_total=int(_number(tier_total)) if tier_total is not None else None,
            special_type=str(raw.get("special_type", "none")),
        )

    @property
    def is_free(self) -> bool:
        return self.price <= 0 and self.total_value > 0

    @property
    def display_name(self) -> str:
        if self.is_tier and self.tier_index:
            suffix = f"{self.tier_index}/{self.tier_total}" if self.tier_total else str(self.tier_index)
            return f"{self.name}（阶梯 {suffix}）"
        return self.name


@dataclass(frozen=True, slots=True)
class RatingRule:
    code: str
    name: str
    min_ratio: float
    max_ratio: float | None
    sort_order: int

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> "RatingRule":
        maximum = raw.get("max_ratio")
        return cls(
            code=str(raw.get("code", "")),
            name=str(raw.get("name", "")),
            min_ratio=_number(raw.get("min_ratio")),
            max_ratio=_number(maximum) if maximum is not None else None,
            sort_order=int(_number(raw.get("sort_order"))),
        )

