"""Controlled importer for user-provided Majsoul data files.

This module deliberately accepts an explicit local JSON file only.  It never
contacts a third party and must not be used to represent fixture data as a
real player profile.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .database import MajsoulDataRepository


class ImportFormatError(ValueError):
    """Raised for a malformed local export before it can reach SQLite."""


@dataclass(frozen=True, slots=True)
class ImportResult:
    players: int
    profiles: int
    records: int


def load_local_file(path: Path) -> dict[str, Any]:
    """Read a deliberately supplied JSON export; no network fallback exists."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ImportFormatError("无法读取合法的本地 JSON 导入文件。") from exc
    if not isinstance(raw, dict) or not isinstance(raw.get("players"), list):
        raise ImportFormatError("导入文件必须是包含 players 数组的 JSON 对象。")
    return raw


async def import_local_file(repository: MajsoulDataRepository, path: Path) -> ImportResult:
    payload = load_local_file(path)
    counts = await repository.import_payload(payload, source_path=path.name)
    return ImportResult(**counts)
