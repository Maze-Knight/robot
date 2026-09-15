from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .models import DrawRecord


class DailyDrawCardRenderer:
    WIDTH = 1000
    HEIGHT = 650

    def __init__(self, asset_dir: Path) -> None:
        self.asset_dir = asset_dir

    @staticmethod
    def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        candidates = (
            Path("C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc"),
            Path("C:/Windows/Fonts/simhei.ttf"),
        )
        for path in candidates:
            if path.is_file():
                return ImageFont.truetype(str(path), size)
        return ImageFont.load_default()

    def render(self, record: DrawRecord) -> bytes:
        canvas = Image.new("RGB", (self.WIDTH, self.HEIGHT), "#0d1b2a")
        draw = ImageDraw.Draw(canvas)
        title_font = self._font(36, bold=True)
        name_font = self._font(21, bold=True)
        small_font = self._font(16)
        draw.text((42, 24), "莫纳提姆 · 每日十连", font=title_font, fill="#f5f7fa")
        draw.text((650, 35), record.draw_date, font=small_font, fill="#91a4b7")

        card_w, card_h = 176, 245
        start_x, start_y, gap_x, gap_y = 42, 90, 16, 22
        rarity_colors = {1: "#8b98a5", 2: "#9b6de3", 3: "#f1b94b"}
        for index, item in enumerate(record.items):
            row, column = divmod(index, 5)
            x = start_x + column * (card_w + gap_x)
            y = start_y + row * (card_h + gap_y)
            color = rarity_colors[item.rarity]
            draw.rounded_rectangle(
                (x, y, x + card_w, y + card_h),
                radius=16,
                fill="#15283a",
                outline=color,
                width=4,
            )
            portrait = self._load_portrait(item.image)
            canvas.paste(portrait, (x + 12, y + 12))
            stars = "★" * item.rarity
            star_box = draw.textbbox((0, 0), stars, font=name_font)
            draw.text(
                (x + (card_w - (star_box[2] - star_box[0])) / 2, y + 172),
                stars,
                font=name_font,
                fill=color,
            )
            self._draw_centered_name(draw, item.name, x, y + 205, card_w, name_font)

        draw.text(
            (42, 620),
            "系统计算完成。结果当然在预期之内。",
            font=small_font,
            fill="#91a4b7",
        )
        output = io.BytesIO()
        canvas.save(output, format="PNG", optimize=True)
        return output.getvalue()

    def _load_portrait(self, relative_path: str) -> Image.Image:
        path = (self.asset_dir / Path(relative_path).name).resolve()
        try:
            if not path.is_relative_to(self.asset_dir.resolve()):
                raise ValueError("invalid portrait path")
            with Image.open(path) as image:
                portrait = image.convert("RGB")
                portrait.thumbnail((152, 152), Image.Resampling.LANCZOS)
                background = Image.new("RGB", (152, 152), "#e9eef3")
                background.paste(
                    portrait,
                    ((152 - portrait.width) // 2, (152 - portrait.height) // 2),
                )
                return background
        except (OSError, ValueError):
            return Image.new("RGB", (152, 152), "#263d52")

    @staticmethod
    def _draw_centered_name(
        draw: ImageDraw.ImageDraw,
        name: str,
        x: int,
        y: int,
        width: int,
        font: ImageFont.ImageFont,
    ) -> None:
        display = name if len(name) <= 9 else name[:8] + "…"
        box = draw.textbbox((0, 0), display, font=font)
        draw.text(
            (x + (width - (box[2] - box[0])) / 2, y),
            display,
            font=font,
            fill="#f5f7fa",
        )
