from __future__ import annotations

import os
import re
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from .database import MajsoulDataRepository, StoredPlayer, StoredProfile
from .providers import EmptyProvider, MajsoulDataProvider

_PLAYER_ID = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
DEFAULT_DATABASE_PATH = Path(
    os.getenv("MAJSOUL_DATA_DATABASE_PATH", "data/majsoul_data_service.sqlite3")
)


class PlayerResponse(BaseModel):
    amae_player_id: str
    nickname: str | None
    source: str
    synced_at: str | None


class ProfileResponse(BaseModel):
    amae_player_id: str
    nickname: str | None
    mode: str
    level_id: int | None
    level_score: int | None
    total_games: int | None
    average_rank: float | None
    negative_rate: float | None
    source: str
    source_record_id: str | None
    synced_at: str


def _validate_player_id(amae_player_id: str) -> str:
    if not _PLAYER_ID.fullmatch(amae_player_id):
        raise HTTPException(422, {"code": "invalid_player_id", "message": "amae_player_id 格式无效"})
    return amae_player_id


def _not_synced(amae_player_id: str, mode: str | None = None) -> HTTPException:
    detail: dict[str, str] = {
        "code": "not_synced",
        "message": "该玩家尚未同步到本地数据服务。",
        "amae_player_id": amae_player_id,
    }
    if mode is not None:
        detail["mode"] = mode
    return HTTPException(404, detail)


def _player_response(player: StoredPlayer) -> PlayerResponse:
    return PlayerResponse(
        amae_player_id=player.amae_player_id,
        nickname=player.nickname,
        source=player.source,
        synced_at=player.synced_at,
    )


def _profile_response(profile: StoredProfile) -> ProfileResponse:
    return ProfileResponse(
        amae_player_id=profile.amae_player_id,
        nickname=profile.nickname,
        mode=profile.mode,
        level_id=profile.level_id,
        level_score=profile.level_score,
        total_games=profile.total_games,
        average_rank=profile.average_rank,
        negative_rate=profile.negative_rate,
        source=profile.source,
        source_record_id=profile.source_record_id,
        synced_at=profile.synced_at,
    )


def create_app(
    database_path: Path = DEFAULT_DATABASE_PATH,
    provider: MajsoulDataProvider | None = None,
) -> FastAPI:
    repository = MajsoulDataRepository(database_path)
    active_provider = provider or EmptyProvider()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        await repository.initialize()
        yield

    app = FastAPI(title="Elena Majsoul Data Service", version="0.1.0", lifespan=lifespan)
    app.state.repository = repository
    app.state.provider = active_provider

    @app.get("/health")
    async def health() -> dict[str, str]:
        database_status = "ok" if await repository.health() else "unavailable"
        return {
            "service": "majsoul-data-service",
            "status": "ok" if database_status == "ok" else "degraded",
            "database": database_status,
            "provider": active_provider.name,
        }

    @app.get("/v1/players/{amae_player_id}", response_model=PlayerResponse)
    async def player(amae_player_id: str) -> PlayerResponse:
        player_id = _validate_player_id(amae_player_id)
        stored = await repository.get_player(player_id)
        if stored is None:
            raise _not_synced(player_id)
        return _player_response(stored)

    @app.get("/v1/players/{amae_player_id}/profile", response_model=ProfileResponse)
    async def profile(
        amae_player_id: str,
        mode: str = Query(..., pattern="^(four|three)$"),
    ) -> ProfileResponse:
        player_id = _validate_player_id(amae_player_id)
        stored = await repository.get_profile(player_id, mode)
        if stored is None:
            raise _not_synced(player_id, mode)
        return _profile_response(stored)

    return app


app = create_app()
