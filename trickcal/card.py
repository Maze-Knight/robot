"""Image card for the remote Trickcal board's attribute summary."""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .models import TrickcalAttributeStat, TrickcalSummary


class TrickcalProgressCardRenderer:
    """Render a compact, mobile-readable summary without website assets."""

    WIDTH = 960
    HEIGHT = 940
    _ORDER = (
        ("attack", "攻击力", "攻", "#F47A4A"),
        ("critical", "暴击", "暴", "#E95E68"),
        ("health", "生命值", "生", "#65A83D"),
        ("defense", "防御力", "防", "#7864D6"),
        ("critical_resistance", "暴击抗性", "抗", "#C36376"),
    )

    @staticmethod
    def _font(size: int, *, bold: bool = False) -> ImageFont.ImageFont:
        candidates = (
            Path(r"C:\Windows\Fonts\msyhbd.ttc" if bold else r"C:\Windows\Fonts\msyh.ttc"),
            Path(r"C:\Windows\Fonts\simhei.ttf"),
        )
        for path in candidates:
            if path.is_file():
                try:
                    return ImageFont.truetype(str(path), size)
                except OSError:
                    continue
        return ImageFont.load_default()

    def render(self, summary: TrickcalSummary) -> bytes:
        image = Image.new("RGB", (self.WIDTH, self.HEIGHT), "#FBF6E8")
        draw = ImageDraw.Draw(image)
        title_font = self._font(42, bold=True)
        heading_font = self._font(29, bold=True)
        metric_font = self._font(38, bold=True)
        label_font = self._font(22)
        row_font = self._font(27, bold=True)
        detail_font = self._font(20)

        draw.rounded_rectangle((28, 24, 932, 150), radius=26, fill="#FFFDF6")
        draw.text((62, 52), "莫纳提姆市政终端", font=label_font, fill="#667080")
        draw.text((62, 82), "蜡笔板 · 属性统计", font=title_font, fill="#243C62")
        draw.rounded_rectangle((772, 61, 890, 113), radius=20, fill="#FF6B00")
        draw.text((797, 73), "总览", font=label_font, fill="#FFFFFF")

        metrics = (
            ("已用金蜡笔", self._number(summary.gold_crayons_used)),
            ("已点亮格子", self._ratio(summary.completed_nodes, summary.total_nodes)),
            ("预计还需金蜡笔", self._number(summary.gold_crayons_required)),
            ("当前总加成", f"+{self._percent(sum(item.bonus_percent for item in summary.attribute_stats))}%"),
        )
        for index, (label, value) in enumerate(metrics):
            row, col = divmod(index, 2)
            x, y = 30 + col * 455, 176 + row * 132
            fill = "#FFF1E4" if index == 2 else "#EAE6F0"
            draw.rounded_rectangle((x, y, x + 425, y + 106), radius=22, fill=fill)
            draw.text((x + 26, y + 19), label, font=label_font, fill="#526077")
            draw.text(
                (x + 26, y + 54),
                value,
                font=metric_font,
                fill="#ED6204" if index == 2 else "#243C62",
            )

        draw.text((38, 458), "按属性统计", font=heading_font, fill="#243C62")
        stat_by_key = {item.key: item for item in summary.attribute_stats}
        for index, (key, fallback_label, badge, accent) in enumerate(self._ORDER):
            stat = stat_by_key.get(key) or TrickcalAttributeStat(
                key, fallback_label, 0, 0, 0
            )
            y = 510 + index * 79
            draw.rounded_rectangle((30, y, 930, y + 62), radius=19, fill="#EAE6F0")
            draw.ellipse((52, y + 10, 94, y + 52), fill=accent)
            badge_box = draw.textbbox((0, 0), badge, font=label_font)
            draw.text(
                (73 - (badge_box[2] - badge_box[0]) / 2, y + 16),
                badge,
                font=label_font,
                fill="#FFFFFF",
            )
            draw.text((116, y + 16), stat.label, font=row_font, fill="#243C62")
            draw.text(
                (340, y + 20),
                f"已点亮 {max(0, stat.lit_nodes)} / {max(0, stat.total_nodes)}",
                font=detail_font,
                fill="#687386",
            )
            draw.text(
                (775, y + 16),
                f"+{self._percent(stat.bonus_percent)}%",
                font=row_font,
                fill="#243C62",
            )

        draw.text(
            (38, 905),
            "正常运行。属性账目都按本市长的规则计算。",
            font=detail_font,
            fill="#687386",
        )
        output = io.BytesIO()
        image.save(output, format="PNG", optimize=True)
        return output.getvalue()

    @staticmethod
    def _number(value: int | None) -> str:
        return f"{value:,}" if value is not None else "—"

    @staticmethod
    def _ratio(current: int | None, total: int | None) -> str:
        if current is None or total is None:
            return "—"
        return f"{current} / {total}"

    @staticmethod
    def _percent(value: float) -> str:
        return f"{value:g}"
