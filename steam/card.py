from __future__ import annotations

import asyncio
import logging
import os
import unicodedata
from functools import lru_cache
from io import BytesIO
from typing import Any

from PIL import Image, ImageDraw, ImageFont, ImageOps

from .service import PlayerResult


logger = logging.getLogger("elena.qq.steam")


@lru_cache(maxsize=32)
def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    candidates = (
        [r"C:\Windows\Fonts\msyhbd.ttc", r"C:\Windows\Fonts\simhei.ttf"]
        if bold
        else [r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\simsun.ttc"]
    )
    candidates.extend(
        [
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
    )
    for filename in candidates:
        if os.path.isfile(filename):
            try:
                return ImageFont.truetype(filename, size=size)
            except OSError:
                continue
    return ImageFont.load_default(size=size)


@lru_cache(maxsize=16)
def _symbol_font(size: int) -> ImageFont.ImageFont | None:
    for filename in (
        r"C:\Windows\Fonts\cambria.ttc",
        r"C:\Windows\Fonts\seguisym.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuMathTeXGyre.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        if os.path.isfile(filename):
            try:
                return ImageFont.truetype(filename, size=size)
            except OSError:
                continue
    return None


def _draw_name(
    draw: ImageDraw.ImageDraw,
    text: str,
    *,
    x: int,
    y: int,
    max_width: int,
) -> None:
    primary = _font(42, True)
    symbol = _symbol_font(42)
    right = x + max_width
    for char in text.replace("\ufe0f", ""):
        special = 0x1D400 <= ord(char) <= 0x1D7FF
        selected = symbol if special and symbol is not None else primary
        rendered = unicodedata.normalize("NFKC", char) if special and symbol is None else char
        width = float(draw.textlength(rendered, font=selected))
        if x + width > right:
            draw.text((x, y), "…", font=primary, fill=(245, 248, 250))
            break
        draw.text((x, y), rendered, font=selected, fill=(245, 248, 250))
        x += int(width)


def _fit_text(
    draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, width: int
) -> str:
    value = str(text or "").replace("\ufe0f", "")
    if draw.textbbox((0, 0), value, font=font)[2] <= width:
        return value
    while value and draw.textbbox((0, 0), value + "…", font=font)[2] > width:
        value = value[:-1]
    return value + "…"


def _gradient(width: int, height: int) -> Image.Image:
    top, bottom = (23, 35, 50), (12, 20, 30)
    image = Image.new("RGB", (width, height), top)
    draw = ImageDraw.Draw(image)
    for y in range(height):
        ratio = y / max(1, height - 1)
        color = tuple(int(top[i] * (1 - ratio) + bottom[i] * ratio) for i in range(3))
        draw.line((0, y, width, y), fill=color)
    return image


async def _download_image(
    http_client: Any, url: str, *, max_bytes: int = 6 * 1024 * 1024
) -> Image.Image | None:
    if not url.startswith(("https://", "http://")):
        return None
    try:
        response = await http_client.get(url, timeout=12.0)
        response.raise_for_status()
        if len(response.content) > max_bytes:
            return None
        image = Image.open(BytesIO(response.content))
        image.load()
        return image.convert("RGB")
    except Exception as exc:
        logger.warning("[STEAM] card asset unavailable | error=%s", type(exc).__name__)
        return None


def _paste_avatar(base: Image.Image, avatar: Image.Image | None) -> None:
    size = (160, 160)
    source = (
        ImageOps.fit(avatar, size, method=Image.Resampling.LANCZOS)
        if avatar is not None
        else Image.new("RGB", size, (58, 85, 110))
    )
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, 159, 159), radius=24, fill=255)
    base.paste(source, (58, 75), mask)


class SteamCardRenderer:
    """Render the migrated Steam avatar/status card without QQ dependencies."""

    def __init__(self, http_client: Any) -> None:
        self._http = http_client

    async def render(self, mode: str, result: PlayerResult) -> bytes:
        player = result.player
        cover_url = (
            f"https://cdn.akamai.steamstatic.com/steam/apps/{player.game_id}/header.jpg"
            if player.game_id
            else ""
        )
        avatar, cover = await asyncio.gather(
            _download_image(self._http, player.avatar_url),
            _download_image(self._http, cover_url),
        )

        image = _gradient(820, 330)
        if cover is not None:
            image = ImageOps.fit(
                cover, image.size, method=Image.Resampling.LANCZOS
            ).convert("RGBA")
            image = Image.alpha_composite(
                image, Image.new("RGBA", image.size, (4, 12, 20, 102))
            )
        else:
            image = image.convert("RGBA")

        panel = Image.new("RGBA", image.size, (0, 0, 0, 0))
        panel_draw = ImageDraw.Draw(panel)
        panel_draw.rounded_rectangle(
            (28, 26, 792, 304),
            radius=24,
            fill=(11, 27, 40, 200),
            outline=(45, 145, 199, 235),
            width=2,
        )
        image = Image.alpha_composite(image, panel).convert("RGB")
        _paste_avatar(image, avatar)

        draw = ImageDraw.Draw(image)
        title = "STEAM 实时状态" if mode == "status" else "STEAM 用户档案"
        draw.text((252, 64), title, font=_font(25, True), fill=(102, 192, 244))
        _draw_name(draw, player.name, x=252, y=105, max_width=500)
        status = (
            f"正在玩：{player.game_name or '未知游戏'}"
            if player.game_id
            else f"当前状态：{player.presence}"
        )
        status_color = (159, 213, 96) if player.game_id else (190, 202, 214)
        status_font = _font(28)
        draw.text(
            (252, 172),
            _fit_text(draw, status, status_font, 500),
            font=status_font,
            fill=status_color,
        )
        footer = (
            f"SteamID  {player.steam_id}"
            if mode == "profile"
            else "莫纳提姆市政终端 · Steam 监测站"
        )
        draw.text((58, 262), footer, font=_font(20), fill=(137, 158, 177))

        output = BytesIO()
        image.save(output, format="PNG", optimize=True)
        return output.getvalue()
