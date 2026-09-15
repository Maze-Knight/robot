from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import httpx


PROJECT_ROOT = Path(__file__).resolve().parents[1]
POOL_PATH = PROJECT_ROOT / "daily_draw_pool.json"
ASSET_DIR = PROJECT_ROOT / "daily_draw_assets"
SOURCE_PAGE = "https://www.gamekee.com/tr/second/127885"
TREE_API = "https://www.gamekee.com/v1/entry/getEntryTreeById?id=127885"
SECTION_KEYS = {
    "韩服3星使徒": "three_star",
    "韩服2星使徒": "two_star",
    "韩服1星使徒": "one_star",
}


def main() -> None:
    headers = {
        "X-Requested-With": "XMLHttpRequest",
        "game-alias": "tr",
        "Lang": "zh-cn",
        "device-num": "1",
        "Referer": SOURCE_PAGE,
    }
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    with httpx.Client(headers=headers, timeout=30, follow_redirects=True) as client:
        response = client.get(TREE_API)
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != 0:
            raise RuntimeError(f"GameKee API error: {payload.get('code')} {payload.get('msg')}")
        sections = {section.get("name"): section for section in payload["data"]}
        result: dict[str, object] = {
            "source": SOURCE_PAGE,
            "server": "韩服",
            "synced_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        for section_name, key in SECTION_KEYS.items():
            section = sections.get(section_name)
            if section is None:
                raise RuntimeError(f"Missing GameKee section: {section_name}")
            items: list[dict[str, str]] = []
            for entry in section.get("child") or []:
                source_name = str(entry.get("name", "")).strip()
                icon = str(entry.get("icon", "")).strip()
                if not source_name or source_name == "???" or not icon:
                    continue
                item_id = str(entry["id"])
                display_name = source_name.split("/", 1)[0].strip()
                image_url = "https:" + icon if icon.startswith("//") else icon
                image_name = f"{item_id}.png"
                image_response = client.get(image_url)
                image_response.raise_for_status()
                (ASSET_DIR / image_name).write_bytes(image_response.content)
                items.append(
                    {
                        "id": item_id,
                        "name": display_name,
                        "source_name": source_name,
                        "image": image_name,
                        "source_image": image_url,
                    }
                )
            result[key] = items
            print(f"{section_name}: {len(items)}")
    POOL_PATH.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"pool: {POOL_PATH}")
    print(f"assets: {ASSET_DIR}")


if __name__ == "__main__":
    main()
