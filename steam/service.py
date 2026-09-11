from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from .client import SteamClient
from .models import OfficialIdentity, SteamPlayer
from .repository import SteamRepository


logger = logging.getLogger("elena.qq.steam")


@dataclass(frozen=True, slots=True)
class PlayerResult:
    player: SteamPlayer
    observed_game_since: datetime | None = None


class SteamService:
    def __init__(self, client: SteamClient, repository: SteamRepository) -> None:
        self.client = client
        self.repository = repository

    async def register_identity(
        self, identity: OfficialIdentity, raw_steam_identity: str
    ) -> SteamPlayer:
        steam_id = await self.client.resolve_steam_id(raw_steam_identity)
        player = await self.client.fetch_player(steam_id)
        await self.repository.save_binding(identity, steam_id)
        logger.info(
            "[STEAM] binding saved | scene_group=%s | user_id=%s | steam_id=%s",
            bool(identity.group_id), identity.user_id, steam_id,
        )
        return player

    async def get_profile(self, identity: OfficialIdentity) -> PlayerResult | None:
        binding = await self.repository.get_binding(identity)
        if binding is None:
            return None
        logger.info("[STEAM] user resolved | steam_id=%s", binding.steam_id)
        player = await self.client.fetch_player(binding.steam_id)
        since = await self.repository.observe_game(identity, player.game_id)
        return PlayerResult(player, since)

    async def unregister_identity(self, identity: OfficialIdentity) -> bool:
        removed = await self.repository.delete_binding(identity)
        logger.info(
            "[STEAM] binding removed | scene_group=%s | user_id=%s | existed=%s",
            bool(identity.group_id), identity.user_id, removed,
        )
        return removed

