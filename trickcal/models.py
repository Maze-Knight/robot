from __future__ import annotations

from dataclasses import dataclass
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
class TrickcalSummary:
    profile_exists: bool | None = None
    owned_characters: int | None = None
    total_characters: int | None = None
    completed_nodes: int | None = None
    total_nodes: int | None = None
    planned_nodes: int | None = None
    gold_required: int | None = None
    gold_crayons_required: int | None = None
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
            updated_at=payload.get("updated_at") if isinstance(payload.get("updated_at"), str) else None,
        )
