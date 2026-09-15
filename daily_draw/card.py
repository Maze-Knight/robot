from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .models import CollectionSnapshot, DrawRecord


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

    def render_collection(self, snapshot: CollectionSnapshot) -> bytes:
        columns = 15
        tile_w, tile_h = 112, 125
        gap_x, gap_y = 8, 10
        start_x, start_y = 35, 150
        rows = (len(snapshot.entries) + columns - 1) // columns
        width = start_x * 2 + columns * tile_w + (columns - 1) * gap_x
        height = start_y + rows * tile_h + (rows - 1) * gap_y + 42
        canvas = Image.new("RGB", (width, height), "#dceaff")
        draw = ImageDraw.Draw(canvas)
        title_font = self._font(42, bold=True)
        stat_font = self._font(24, bold=True)
        name_font = self._font(14, bold=True)
        star_font = self._font(14, bold=True)

        draw.text((35, 28), "使徒图鉴 · 圣团档案", font=title_font, fill="#5b4269")
        progress_x, progress_y, progress_w = width - 630, 38, 560
        draw.rounded_rectangle(
            (progress_x, progress_y, progress_x + progress_w, progress_y + 30),
            radius=15,
            fill="#f7f9fc",
        )
        filled = round(progress_w * snapshot.completion_percent / 100)
        if filled:
            draw.rounded_rectangle(
                (progress_x, progress_y, progress_x + filled, progress_y + 30),
                radius=15,
                fill="#ff6685",
            )
        draw.text(
            (progress_x + 45, 82),
            f"已收集 {snapshot.unlocked_count} / {snapshot.total_count}  |  "
            f"{snapshot.completion_percent:.2f}%",
            font=stat_font,
            fill="#27384a",
        )

        colors = {1: "#8b98a5", 2: "#9b6de3", 3: "#f1b94b"}
        for index, entry in enumerate(snapshot.entries):
            row, column = divmod(index, columns)
            x = start_x + column * (tile_w + gap_x)
            y = start_y + row * (tile_h + gap_y)
            if not entry.unlocked:
                draw.rounded_rectangle(
                    (x, y, x + tile_w, y + tile_h),
                    radius=10,
                    fill="#f4f6f9",
                    outline="#c9d2dc",
                    width=2,
                )
                self._draw_lock(draw, x + tile_w // 2, y + 43)
                self._draw_centered_name(draw, "未解锁", x, y + 96, tile_w, name_font)
                continue
            color = colors.get(min(entry.item.rarity, 3), colors[3])
            draw.rounded_rectangle(
                (x, y, x + tile_w, y + tile_h),
                radius=10,
                fill="#ffffff",
                outline=color,
                width=3,
            )
            portrait = self._load_portrait(entry.item.image, size=78)
            canvas.paste(portrait, (x + 17, y + 8))
            level = f"★×{entry.current_stars}"
            level_box = draw.textbbox((0, 0), level, font=star_font)
            draw.rounded_rectangle(
                (x + 5, y + 5, x + 13 + level_box[2], y + 27),
                radius=8,
                fill=color,
            )
            draw.text((x + 9, y + 6), level, font=star_font, fill="#ffffff")
            self._draw_centered_name(
                draw,
                entry.item.name,
                x,
                y + 94,
                tile_w,
                name_font,
                fill="#27384a",
            )

        output = io.BytesIO()
        canvas.save(output, format="PNG", optimize=True)
        return output.getvalue()

    @staticmethod
    def _draw_lock(draw: ImageDraw.ImageDraw, center_x: int, top_y: int) -> None:
        color = "#a7afb8"
        draw.rounded_rectangle(
            (center_x - 20, top_y + 18, center_x + 20, top_y + 56),
            radius=7,
            fill=color,
        )
        draw.arc(
            (center_x - 15, top_y, center_x + 15, top_y + 34),
            180,
            360,
            fill=color,
            width=7,
        )
        draw.ellipse(
            (center_x - 4, top_y + 32, center_x + 4, top_y + 40),
            fill="#f4f6f9",
        )

    def _load_portrait(self, relative_path: str, *, size: int = 152) -> Image.Image:
        path = (self.asset_dir / Path(relative_path).name).resolve()
        try:
            if not path.is_relative_to(self.asset_dir.resolve()):
                raise ValueError("invalid portrait path")
            with Image.open(path) as image:
                portrait = image.convert("RGB")
                portrait.thumbnail((size, size), Image.Resampling.LANCZOS)
                background = Image.new("RGB", (size, size), "#e9eef3")
                background.paste(
                    portrait,
                    ((size - portrait.width) // 2, (size - portrait.height) // 2),
                )
                return background
        except (OSError, ValueError):
            return Image.new("RGB", (size, size), "#263d52")

    @staticmethod
    def _draw_centered_name(
        draw: ImageDraw.ImageDraw,
        name: str,
        x: int,
        y: int,
        width: int,
        font: ImageFont.ImageFont,
        *,
        fill: str = "#f5f7fa",
    ) -> None:
        display = name if len(name) <= 9 else name[:8] + "…"
        box = draw.textbbox((0, 0), display, font=font)
        draw.text(
            (x + (width - (box[2] - box[0])) / 2, y),
            display,
            font=font,
            fill=fill,
        )
