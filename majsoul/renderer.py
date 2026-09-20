from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .models import MajsoulPlayerCardData, RecentGame, rank_label


class MajsoulCardRenderer:
    WIDTH = 1080

    @staticmethod
    def _font(size: int, *, bold: bool = False) -> ImageFont.ImageFont:
        candidates = [
            Path("C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc"),
            Path("C:/Windows/Fonts/simhei.ttf"),
            Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc" if bold else "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        ]
        for candidate in candidates:
            if candidate.is_file():
                return ImageFont.truetype(str(candidate), size)
        return ImageFont.load_default()

    def render(self, data: MajsoulPlayerCardData) -> bytes:
        height = 1540
        image = Image.new("RGB", (self.WIDTH, height), "#081426")
        draw = ImageDraw.Draw(image)
        title = self._font(42, bold=True)
        name = self._font(58, bold=True)
        heading = self._font(30, bold=True)
        metric = self._font(34, bold=True)
        label = self._font(22)
        small = self._font(18)

        draw.rounded_rectangle((25, 25, 1055, height - 25), radius=34, fill="#10233f", outline="#245e9c", width=2)
        draw.text((62, 62), "🀄 雀魂玩家档案", font=title, fill="#81c8ff")
        draw.text((62, 125), data.nickname[:20], font=name, fill="#f5f8ff")
        family = "三麻" if data.mode_family == "three" else "四麻"
        draw.rounded_rectangle((830, 132, 1002, 187), radius=18, fill="#1b4f82")
        self._center(draw, family, 830, 144, 172, label, "#d8efff")

        stats = data.stats
        draw.rounded_rectangle((62, 225, 1018, 410), radius=24, fill="#142d4d")
        draw.text((92, 255), rank_label(stats.level_id), font=self._font(54, bold=True), fill="#7bc4ff")
        draw.text((95, 330), f"段位分  {stats.level_score:,}", font=heading, fill="#f2f6ff")
        draw.text((520, 265), f"记录场数  {stats.total_games:,}", font=heading, fill="#f2f6ff")
        updated = self._format_time(stats.updated_at)
        draw.text((520, 330), f"数据更新  {updated}", font=label, fill="#b2c2d8")

        first_rate = stats.rank_rates[0] if stats.rank_rates else None
        primary = (("一位率", first_rate), ("和牌率", self._value(stats.extended, "和牌率")), ("放铳率", self._value(stats.extended, "放铳率")))
        self._metric_row(draw, primary, 62, 445, 956, 132, metric, label)
        secondary = (("自摸率", self._value(stats.extended, "自摸率")), ("副露率", self._value(stats.extended, "副露率")), ("立直率", self._value(stats.extended, "立直率")), ("被飞率", stats.negative_rate))
        self._metric_row(draw, secondary, 62, 600, 956, 118, metric, label)
        tertiary = (("平均顺位", stats.average_rank, "fixed"), ("平均打点", self._value(stats.extended, "平均打点"), "number"), ("最大连庄", self._value(stats.extended, "最大连庄"), "number"), ("平均和牌巡", self._value(stats.extended, "和了巡数"), "fixed"))
        self._metric_row(draw, tertiary, 62, 740, 956, 118, metric, label)

        draw.text((62, 900), "最近 20 场比赛", font=heading, fill="#f2f6ff")
        for index, game in enumerate(data.recent_games[:20]):
            row, col = divmod(index, 10)
            x, y = 62 + col * 94, 955 + row * 82
            fill = {1: "#3284ec", 2: "#38609a", 3: "#263d60", 4: "#182a45"}.get(game.rank, "#182a45")
            draw.rounded_rectangle((x, y, x + 78, y + 64), radius=12, fill=fill)
            self._center(draw, f"#{game.rank}" if game.rank else "—", x, y + 14, 78, metric, "#ffffff")

        bottom = 1150
        draw.text((62, bottom), "最近对局", font=heading, fill="#f2f6ff")
        games = data.recent_games[:5]
        if not games:
            draw.text((62, bottom + 58), "暂无可用对局记录", font=label, fill="#b2c2d8")
        for index, game in enumerate(games):
            y = bottom + 52 + index * 58
            draw.rounded_rectangle((62, y, 1018, y + 46), radius=10, fill="#142d4d")
            draw.text((82, y + 11), f"#{game.rank or '—'}", font=label, fill="#7bc4ff")
            draw.text((180, y + 11), game.mode_label, font=label, fill="#dce8f8")
            draw.text((445, y + 11), f"最终点数 {game.score:,}" if game.score is not None else "最终点数 —", font=label, fill="#dce8f8")
            draw.text((760, y + 11), self._relative_time(game.started_at), font=label, fill="#aabbd2")

        draw.text((62, height - 65), "数据来源：雀魂牌谱屋 · amae-koromo.sapk.ch", font=small, fill="#7890ad")
        output = io.BytesIO()
        image.save(output, format="PNG", optimize=True)
        return output.getvalue()

    @staticmethod
    def _value(mapping: dict[str, float | int], key: str) -> float | int | None:
        return mapping.get(key)

    def _metric_row(self, draw: ImageDraw.ImageDraw, values: tuple, x: int, y: int, width: int, height: int, metric: ImageFont.ImageFont, label: ImageFont.ImageFont) -> None:
        count = len(values)
        gap = 12
        cell = (width - gap * (count - 1)) // count
        for index, item in enumerate(values):
            item_label, value, *style = item
            left = x + index * (cell + gap)
            draw.rounded_rectangle((left, y, left + cell, y + height), radius=18, fill="#142d4d")
            text = self._format_metric(value, style[0] if style else "percent")
            self._center(draw, text, left, y + 25, cell, metric, "#f4f8ff")
            self._center(draw, item_label, left, y + height - 35, cell, label, "#aabbd2")

    @staticmethod
    def _format_metric(value: float | int | None, style: str) -> str:
        if value is None:
            return "—"
        if style == "number":
            return f"{int(value):,}"
        if style == "fixed":
            return f"{float(value):.2f}"
        return f"{float(value) * 100:.2f}%"

    @staticmethod
    def _center(draw: ImageDraw.ImageDraw, text: str, x: int, y: int, width: int, font: ImageFont.ImageFont, fill: str) -> None:
        box = draw.textbbox((0, 0), text, font=font)
        draw.text((x + (width - (box[2] - box[0])) / 2, y), text, font=font, fill=fill)

    @staticmethod
    def _format_time(value: datetime | None) -> str:
        return value.astimezone().strftime("%Y-%m-%d %H:%M") if value else "以牌谱屋数据为准"

    @staticmethod
    def _relative_time(value: datetime | None) -> str:
        if value is None:
            return "时间未知"
        seconds = max(0, int((datetime.now(value.tzinfo) - value).total_seconds()))
        if seconds < 3600:
            return f"{max(1, seconds // 60)} 分钟前"
        if seconds < 86400:
            return f"{seconds // 3600} 小时前"
        return f"{seconds // 86400} 天前"
