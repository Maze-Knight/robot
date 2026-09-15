from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .catalog import DrawCatalog
from .engine import DrawEngine
from .models import DrawIdentity, DrawRecord
from .repository import DrawRepository


CHINA_TZ = timezone(timedelta(hours=8))


@dataclass(frozen=True, slots=True)
class DrawOutcome:
    state: str
    record: DrawRecord | None = None


class DailyDrawService:
    def __init__(
        self,
        catalog: DrawCatalog,
        repository: DrawRepository,
        engine: DrawEngine | None = None,
    ) -> None:
        self.catalog = catalog
        self.repository = repository
        self.engine = engine or DrawEngine()

    @staticmethod
    def today(now: datetime | None = None) -> str:
        value = now or datetime.now(CHINA_TZ)
        return value.astimezone(CHINA_TZ).date().isoformat()

    async def get_today(self, identity: DrawIdentity) -> DrawRecord | None:
        return await self.repository.get(identity, self.today())

    async def draw(self, identity: DrawIdentity) -> DrawOutcome:
        draw_date = self.today()
        existing = await self.repository.get(identity, draw_date)
        if existing is not None:
            return DrawOutcome("already_drawn", existing)
        if not self.catalog.ready:
            return DrawOutcome("pool_not_ready")
        record = DrawRecord(
            identity=identity,
            draw_date=draw_date,
            items=self.engine.draw_ten(self.catalog),
            created_at=datetime.now(CHINA_TZ).isoformat(timespec="seconds"),
        )
        stored, inserted = await self.repository.save_if_absent(record)
        return DrawOutcome("drawn" if inserted else "already_drawn", stored)

