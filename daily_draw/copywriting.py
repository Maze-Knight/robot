from __future__ import annotations

from .models import DrawRecord


HOME = """# 🎲 每日抽取

每天可进行一次十连。

概率参数：★★★ 3%｜★★ 21%｜★ 76%

十连至少出现一个 ★★ 或以上。规则已经校准，照着抽就行。"""

POOL_NOT_READY = """# 🎲 每日抽取

抽取名单还没装填。

概率系统已经校准，但本市长不会拿空白数据糊弄你。本次不消耗今日次数。"""

NO_RECORD = """# 📜 今日抽取记录

今天还没有进行十连。名单装填完成后再来。"""


def record_text(record: DrawRecord, *, already_drawn: bool = False) -> str:
    heading = "今天已经抽过了。以下是记录：" if already_drawn else "抽取完成。结果当然已经算好了。"
    lines = [
        f"{index}. {'★' * item.rarity} **{item.name}**"
        for index, item in enumerate(record.items, start=1)
    ]
    return f"# 🎲 每日十连\n\n{heading}\n\n" + "\n".join(lines)

