from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


_EMPTY_GAME_IDS = (None, "", "0")
_NETWORK_FLUCTUATION_WINDOW = 180


@dataclass(frozen=True, slots=True)
class GameTransition:
    """Framework-neutral transition retained from the legacy monitor."""

    kind: str
    previous_game_id: str | None
    current_game_id: str | None
    network_fluctuation: bool = False

    @property
    def has_exit(self) -> bool:
        return self.kind in {"exit", "switch"}

    @property
    def has_start(self) -> bool:
        return self.kind in {"start", "switch"}


def classify_game_transition(
    previous_state: Mapping[str, Any] | None,
    current_state: Mapping[str, Any],
    *,
    pending_quit: Mapping[str, Any] | None = None,
    now: int | None = None,
) -> GameTransition:
    previous_game = previous_state.get("gameid") if previous_state else None
    current_game = current_state.get("gameid")
    if previous_state is None:
        kind = "start" if current_game not in _EMPTY_GAME_IDS else "initial"
    elif previous_game and (
        current_game in _EMPTY_GAME_IDS or current_game != previous_game
    ):
        kind = "switch" if current_game not in _EMPTY_GAME_IDS else "exit"
    elif current_game not in _EMPTY_GAME_IDS and current_game != previous_game:
        kind = "start"
    else:
        kind = "unchanged"

    fluctuation = False
    if kind in {"start", "switch"} and pending_quit and now is not None:
        quit_info = pending_quit.get(str(current_game))
        if isinstance(quit_info, Mapping):
            quit_time = quit_info.get("quit_time")
            if (
                isinstance(quit_time, (int, float))
                and 0 <= now - quit_time <= _NETWORK_FLUCTUATION_WINDOW
                and not quit_info.get("notified")
            ):
                fluctuation = True
    return GameTransition(
        kind,
        str(previous_game) if previous_game else None,
        str(current_game) if current_game else None,
        fluctuation,
    )


class SteamMonitor:
    """Phase-two boundary; state logic is ready but no scheduler is started."""

    def __init__(self, enabled: bool = False) -> None:
        self.enabled = enabled

    async def start(self) -> None:
        if not self.enabled:
            return
        raise RuntimeError("Steam automatic monitoring is not active in phase one")
