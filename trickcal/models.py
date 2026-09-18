from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any


@dataclass(frozen=True, slots=True)
class PlatformIdentity:
    """A platform-scoped identity; QQ group and C2C OpenIDs are never guessed merged."""

    id: int
    platform: str
    platform_user_id: str


@dataclass(frozen=True, slots=True)
class BoardProfile:
    id: int
    identity_id: int


# The two models above belong to the legacy local SQLite implementation.
# The remote API models below are intentionally independent from that schema.


@dataclass(frozen=True, slots=True)
class TrickcalIdentity:
    """The exact QQ identity forwarded to the website; never locally merged."""

    platform: str
    user_id: str
    scene_type: str

    def to_payload(self) -> dict[str, str]:
        return {
            "platform": self.platform,
            "user_id": self.user_id,
            "scene_type": self.scene_type,
        }


@dataclass(frozen=True, slots=True)
class LoginTicketResponse:
    url: str


@dataclass(frozen=True, slots=True)
class TrickcalAttributeStat:
    """One website-calculated attribute group for the QQ progress card."""

    key: str
    label: str
    lit_nodes: int
    total_nodes: int
    bonus_percent: float


@dataclass(frozen=True, slots=True)
class TrickcalSummary:
    profile_exists: bool | None = None
    owned_characters: int | None = None
    total_characters: int | None = None
    completed_nodes: int | None = None
    total_nodes: int | None = None
    planned_nodes: int | None = None
    gold_required: int | None = None
    gold_crayons_required: int | None = None
    gold_crayons_used: int | None = None
    attribute_stats: tuple[TrickcalAttributeStat, ...] = ()
    updated_at: str | None = None

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "TrickcalSummary":
        def optional_int(name: str) -> int | None:
            value = payload.get(name)
            if value is None:
                return None
            if isinstance(value, bool):
                return None
            try:
                return int(value)
            except (TypeError, ValueError):
                return None

        def optional_percent(value: Any) -> float | None:
            if isinstance(value, bool):
                return None
            try:
                parsed = float(value)
            except (TypeError, ValueError):
                return None
            return parsed if math.isfinite(parsed) else None

        attribute_stats: list[TrickcalAttributeStat] = []
        raw_stats = payload.get("attribute_stats")
        if isinstance(raw_stats, list):
            for item in raw_stats:
                if not isinstance(item, dict):
                    continue
                key = item.get("key")
                label = item.get("label")
                lit_nodes = item.get("lit_nodes")
                total_nodes = item.get("total_nodes")
                bonus_percent = optional_percent(item.get("bonus_percent"))
                if (
                    not isinstance(key, str)
                    or not key
                    or not isinstance(label, str)
                    or not label
                    or isinstance(lit_nodes, bool)
                    or isinstance(total_nodes, bool)
                    or bonus_percent is None
                ):
                    continue
                try:
                    attribute_stats.append(
                        TrickcalAttributeStat(
                            key=key,
                            label=label,
                            lit_nodes=max(0, int(lit_nodes)),
                            total_nodes=max(0, int(total_nodes)),
                            bonus_percent=bonus_percent,
                        )
                    )
                except (TypeError, ValueError):
                    continue

        exists = payload.get("profile_exists")
        return cls(
            profile_exists=exists if isinstance(exists, bool) else None,
            owned_characters=optional_int("owned_characters"),
            total_characters=optional_int("total_characters"),
            completed_nodes=optional_int("completed_nodes"),
            total_nodes=optional_int("total_nodes"),
            planned_nodes=optional_int("planned_nodes"),
            gold_required=optional_int("gold_required"),
            gold_crayons_required=optional_int("gold_crayons_required"),
            gold_crayons_used=optional_int("gold_crayons_used"),
            attribute_stats=tuple(attribute_stats),
            updated_at=payload.get("updated_at") if isinstance(payload.get("updated_at"), str) else None,
        )
