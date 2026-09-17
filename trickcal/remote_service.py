"""Small application service exposing only website-owned board operations."""

from __future__ import annotations

from .client import TrickcalClient
from .models import LoginTicketResponse, TrickcalIdentity, TrickcalSummary


class TrickcalRemoteService:
    def __init__(self, client: TrickcalClient) -> None:
        self._client = client

    async def create_login_ticket(self, identity: TrickcalIdentity) -> LoginTicketResponse:
        return await self._client.create_login_ticket(identity)

    async def get_summary(self, identity: TrickcalIdentity) -> TrickcalSummary:
        return await self._client.get_summary(identity)
