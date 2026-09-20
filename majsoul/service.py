from __future__ import annotations

from datetime import datetime

from .client import MajsoulClient
from .models import MajsoulBinding, MajsoulIdentity, MajsoulPlayerCardData, PlayerCandidate
from .repository import MajsoulRepository


class MajsoulBindingNotFoundError(LookupError):
    """The current QQ identity has not registered a Majsoul account."""


class MajsoulService:
    def __init__(self, client: MajsoulClient, repository: MajsoulRepository) -> None:
        self.client = client
        self.repository = repository

    async def search(self, nickname: str) -> tuple[PlayerCandidate, ...]:
        return await self.client.search_players(nickname)

    async def bind(self, identity: MajsoulIdentity, candidate: PlayerCandidate) -> MajsoulBinding:
        return await self.repository.bind(identity, candidate)

    async def unbind(self, identity: MajsoulIdentity) -> bool:
        return await self.repository.unbind(identity)

    async def profile(self, identity: MajsoulIdentity, requested_family: str | None = None) -> MajsoulPlayerCardData:
        binding = await self.repository.get(identity)
        if binding is None:
            raise MajsoulBindingNotFoundError("binding not found")
        family = requested_family if requested_family in {"four", "three"} else binding.mode_family
        stats = await self.client.get_stats(binding.amae_player_id, family)
        games = await self.client.get_recent_games(binding.amae_player_id, family)
        return MajsoulPlayerCardData(
            nickname=stats.nickname or binding.nickname,
            player_id=binding.amae_player_id,
            mode_family=family,
            stats=stats,
            recent_games=games,
            generated_at=datetime.now().astimezone(),
        )
