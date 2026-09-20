from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


FOUR_PLAYER_MODES = (16, 12, 9, 15, 11, 8)
THREE_PLAYER_MODES = (26, 24, 22, 25, 23, 21)

MODE_LABELS = {
    16: "王座间", 12: "玉之间", 9: "金之间", 15: "王座东", 11: "玉东", 8: "金东",
    26: "三王座", 24: "三玉", 22: "三金", 25: "三王东", 23: "三玉东", 21: "三金东",
}


def mode_family_from_level(level_id: int) -> str:
    return "three" if level_id // 10000 == 2 else "four"


def rank_label(level_id: int) -> str:
    value = level_id % 10000
    major, minor = divmod(value, 100)
    # Matches amae-koromo's PLAYER_RANKS: 初、士、杰、豪、圣、魂.
    names = {1: "初心", 2: "雀士", 3: "雀杰", 4: "雀豪", 5: "雀圣"}
    if major >= 6:
        return "魂天"
    return f"{names.get(major, '未知段位')}{minor if minor else ''}"


@dataclass(frozen=True, slots=True)
class MajsoulIdentity:
    platform: str
    platform_user_id: str
    scene_type: str


@dataclass(frozen=True, slots=True)
class MajsoulBinding:
    identity: MajsoulIdentity
    amae_player_id: str
    nickname: str
    level_id: int
    mode_family: str
    bound_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class PlayerCandidate:
    player_id: str
    nickname: str
    level_id: int
    latest_timestamp: int
    mode_family: str

    @classmethod
    def from_payload(cls, payload: Any, mode_family: str) -> "PlayerCandidate | None":
        if not isinstance(payload, dict):
            return None
        try:
            player_id = str(payload["id"]).strip()
            nickname = str(payload["nickname"]).strip()
            level = payload["level"]
            level_id = int(level["id"] if isinstance(level, dict) else level)
            latest_timestamp = int(payload.get("latest_timestamp", 0))
        except (KeyError, TypeError, ValueError):
            return None
        if not player_id or not nickname:
            return None
        return cls(player_id, nickname, level_id, latest_timestamp, mode_family)


@dataclass(frozen=True, slots=True)
class MajsoulStats:
    nickname: str
    level_id: int
    level_score: int
    total_games: int
    rank_rates: tuple[float, ...]
    average_rank: float | None
    negative_rate: float | None
    extended: dict[str, float | int]
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class RecentGame:
    mode_id: int
    started_at: datetime | None
    rank: int | None
    score: int | None

    @property
    def mode_label(self) -> str:
        return MODE_LABELS.get(self.mode_id, f"模式 {self.mode_id}")


@dataclass(frozen=True, slots=True)
class MajsoulPlayerCardData:
    nickname: str
    player_id: str
    mode_family: str
    stats: MajsoulStats
    recent_games: tuple[RecentGame, ...]
    generated_at: datetime
