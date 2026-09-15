from __future__ import annotations

from .models import CollectionSnapshot, CollectionUpdate, DrawRecord


HOME = """# 🎲 每日抽取

每天可进行一次十连。

概率参数：★★★ 3%｜★★ 21%｜★ 76%

十连至少出现一个 ★★ 或以上。规则已经校准，照着抽就行。"""

POOL_NOT_READY = """# 🎲 每日抽取

抽取名单还没装填。

概率系统已经校准，但本市长不会拿空白数据糊弄你。本次不消耗今日次数。"""

NO_RECORD = """# 📜 今日抽取记录

今天还没有进行十连。名单装填完成后再来。"""


def record_text(
    record: DrawRecord,
    *,
    already_drawn: bool = False,
    updates: tuple[CollectionUpdate, ...] = (),
) -> str:
    heading = "今天已经抽过了。以下是记录：" if already_drawn else "抽取完成。结果当然已经算好了。"
    lines = [
        f"{index}. {'★' * item.rarity} **{item.name}**"
        for index, item in enumerate(record.items, start=1)
    ]
    result = f"# 🎲 每日十连\n\n{heading}\n\n" + "\n".join(lines)
    if updates:
        new_items = [update.item.name for update in updates if update.is_new]
        upgraded = [
            f"{update.item.name} → {'★' * update.current_stars}（累计 {update.copies} 次）"
            for update in updates
            if not update.is_new or update.copies > 1
        ]
        if new_items:
            result += "\n\n新使徒：" + "、".join(new_items)
        if upgraded:
            result += "\n\n升星：\n" + "\n".join(f"- {line}" for line in upgraded)
    return result


def collection_text(snapshot: CollectionSnapshot) -> str:
    mention = f"<@{snapshot.identity.user_id}>"
    return (
        f"# 📖 {mention} 的圣团\n\n"
        f"已收集：**{snapshot.unlocked_count} / {snapshot.total_count}**\n\n"
        f"收集率：**{snapshot.completion_percent:.2f}%**\n\n"
        "重复使徒会自动升一★。正常运行，毕竟这是本市长设计的。"
    )
