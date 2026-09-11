from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class OfficialIdentity:
    platform: str
    user_id: str
    group_id: str = ""


@dataclass(frozen=True, slots=True)
class SteamBinding:
    identity: OfficialIdentity
    steam_id: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class SteamPlayer:
    steam_id: str
    name: str
    persona_state: int
    game_id: str
    game_name: str
    profile_url: str
    last_logoff: int | None

    @property
    def presence(self) -> str:
        if self.game_id:
            return "游戏中"
        return {
            0: "离线", 1: "在线", 2: "忙碌", 3: "离开", 4: "打盹",
            5: "想交易", 6: "想玩游戏",
        }.get(self.persona_state, "未知")

