from __future__ import annotations

import io
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import httpx
from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[1]
POOL_PATH = PROJECT_ROOT / "daily_draw_pool.json"
ASSET_DIR = PROJECT_ROOT / "daily_draw_assets"
SOURCE_PAGE = "https://crayon-note.vercel.app/checklist.html"
DATA_URL = "https://crayon-note.vercel.app/data_core.js"
CSS_URL = "https://crayon-note.vercel.app/sprites.css"
SHEET_URLS = {
    "冷靜": "https://crayon-note.vercel.app/char_sprites/char_composed.png",
    "憂鬱": "https://crayon-note.vercel.app/char_sprites/char_depressed.png",
    "天真": "https://crayon-note.vercel.app/char_sprites/char_innocence.png",
    "狂亂": "https://crayon-note.vercel.app/char_sprites/char_madness.png",
    "活潑": "https://crayon-note.vercel.app/char_sprites/char_vivacious.png",
}


def _between(text: str, start: str, end: str) -> str:
    begin = text.find(start)
    if begin < 0:
        raise RuntimeError(f"source marker missing: {start}")
    finish = text.find(end, begin)
    if finish < 0:
        raise RuntimeError(f"source marker missing: {end}")
    return text[begin + len(start):finish]


def _parse_characters(data: str) -> list[dict[str, str]]:
    block = _between(data, "const INITIAL_DATA = [", "];" )
    pattern = re.compile(
        r'\{\s*name:\s*"(?P<name>[^"]+)"\s*,\s*'
        r'personality:\s*"(?P<personality>[^"]+)"\s*,\s*'
        r'race:\s*"(?P<race>[^"]+)"',
    )
    characters = [match.groupdict() for match in pattern.finditer(block)]
    if not characters:
        raise RuntimeError("no characters found in INITIAL_DATA")
    return characters


def _parse_spine_map(data: str) -> dict[str, str]:
    block = _between(data, "const SPINE_MAP = {", "};")
    entries = dict(re.findall(r'"([^"]+)"\s*:\s*"([A-Za-z0-9_]+)"', block))
    if not entries:
        raise RuntimeError("SPINE_MAP is empty")
    return entries


def _sprite_box(css: str, slug: str) -> tuple[int, int, int, int]:
    pattern = re.compile(
        rf"\.sprite-{re.escape(slug)}\s*\{{\s*width:\s*(\d+)px;\s*"
        rf"height:\s*(\d+)px;\s*background-position:\s*-(\d+)px\s+-(\d+)px;\s*\}}"
    )
    match = pattern.search(css)
    if match is None:
        raise RuntimeError(f"sprite CSS missing for {slug}")
    width, height, left, top = map(int, match.groups())
    return left, top, width, height


def _get(client: httpx.Client, url: str) -> httpx.Response:
    response = client.get(url)
    response.raise_for_status()
    return response


def main() -> None:
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        data = _get(client, DATA_URL).text
        css = _get(client, CSS_URL).text
        sheets = {
            personality: Image.open(io.BytesIO(_get(client, url).content)).convert("RGBA")
            for personality, url in SHEET_URLS.items()
        }

    characters = _parse_characters(data)
    spine_map = _parse_spine_map(data)
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    items: list[dict[str, object]] = []
    expected_files: set[str] = set()
    seen_slugs: set[str] = set()
    for character in characters:
        name = character["name"]
        personality = character["personality"]
        slug = spine_map.get(name, "")
        if not slug:
            raise RuntimeError(f"SPINE_MAP missing for {name}")
        if slug in seen_slugs:
            raise RuntimeError(f"duplicate sprite id: {slug}")
        if personality not in sheets:
            raise RuntimeError(f"unknown personality for {name}: {personality}")
        seen_slugs.add(slug)
        left, top, width, height = _sprite_box(css, slug)
        portrait = sheets[personality].crop((left, top, left + width, top + height))
        filename = f"{slug}.png"
        portrait.save(ASSET_DIR / filename, format="PNG", optimize=True)
        expected_files.add(filename)
        items.append(
            {
                "id": slug,
                "name": name,
                "image": filename,
                "personality": personality,
                "race": character["race"],
            }
        )

    # Only remove obsolete PNGs after every replacement portrait was generated.
    for old_file in ASSET_DIR.glob("*.png"):
        if old_file.name not in expected_files:
            old_file.unlink()

    payload = {
        "pool_id": "crayon-note-checklist-uniform-v1",
        "source": SOURCE_PAGE,
        "synced_at": datetime.now(timezone.utc).isoformat(),
        "items": items,
    }
    POOL_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Synced {len(items)} uniformly weighted apostles and portraits.")


if __name__ == "__main__":
    main()
