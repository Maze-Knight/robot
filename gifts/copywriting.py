from __future__ import annotations

from .models import Gift, GiftPeriod, RatingRule


NOT_CONFIGURED = """# 🎁 礼包评估终端

数据线路还没有接通。把礼包网站地址写入 `GIFT_API_BASE_URL` 后再来。

这不是计算故障，只是本市长还没收到数据库坐标。"""

SEARCH_GUIDE = """# 🔎 礼包查询说明

发送：`礼包 礼包名称`

例如：`礼包 每周特惠`

名称不必完全一致。输入得足够明确，系统自然会找到。"""


def home(latest: GiftPeriod | None, count: int) -> str:
    latest_line = latest.name if latest else "暂无可用期次"
    return f"""# 🎁 礼包评估终端

已接入 {count} 期礼包数据。

当前最新：**{latest_line}**

价值、价格和推荐等级都已经排好。照着查就行。"""


def period_list(periods: list[GiftPeriod]) -> str:
    if not periods:
        return "# 📚 礼包期次\n\n数据库里还没有可查询的期次。"
    names = "\n".join(f"- {period.name}" for period in periods)
    return f"# 📚 礼包期次\n\n{names}\n\n选择一期，查看该期性价比排名。"


def _fmt(value: float) -> str:
    if value == int(value):
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _rating_name(gift: Gift, rules: dict[str, RatingRule]) -> str:
    rule = rules.get(gift.rating_code)
    return rule.name if rule and rule.name else "未评级"


def ranking(
    period: GiftPeriod,
    gifts: list[Gift],
    rules: dict[str, RatingRule],
    *,
    limit: int = 8,
) -> str:
    visible = [gift for gift in gifts if gift.show_in_ranking]
    free = sorted(
        (gift for gift in visible if gift.is_free),
        key=lambda gift: gift.total_value,
        reverse=True,
    )
    paid = sorted(
        (gift for gift in visible if not gift.is_free),
        key=lambda gift: (gift.ratio, gift.total_value),
        reverse=True,
    )
    ordered = free + paid
    if not ordered:
        return f"# 🎁 {period.name}\n\n这一期还没有可展示的礼包数据。"

    lines: list[str] = []
    for index, gift in enumerate(ordered[:limit], start=1):
        rating = _rating_name(gift, rules)
        if gift.is_free:
            metrics = f"免费｜价值 {_fmt(gift.total_value)} 叶｜{rating}"
        else:
            metrics = (
                f"¥{_fmt(gift.price)}｜价值 {_fmt(gift.total_value)} 叶｜"
                f"{_fmt(gift.ratio)} 叶/元｜{rating}"
            )
        lines.append(f"**{index}. {gift.display_name}**\n{metrics}")

    omitted = len(ordered) - min(len(ordered), limit)
    footer = f"\n\n另有 {omitted} 项未展开。" if omitted else ""
    return (
        f"# 🎁 {period.name} · 性价比排行\n\n"
        + "\n\n".join(lines)
        + footer
        + "\n\n排序口径：免费礼包优先；付费礼包按每元折算水晶叶降序。"
    )


def search_results(
    keyword: str, gifts: list[Gift], rules: dict[str, RatingRule]
) -> str:
    if not gifts:
        return f"# 🔎 查询：{keyword}\n\n没有匹配结果。换个更短的名称再试。"
    lines: list[str] = []
    for gift in gifts[:8]:
        rating = _rating_name(gift, rules)
        metrics = (
            f"免费｜价值 {_fmt(gift.total_value)} 叶｜{rating}"
            if gift.is_free
            else f"¥{_fmt(gift.price)}｜{_fmt(gift.ratio)} 叶/元｜{rating}"
        )
        lines.append(f"**{gift.display_name}**\n{metrics}")
    return f"# 🔎 查询：{keyword}\n\n" + "\n\n".join(lines)


def error_text(message: str) -> str:
    return f"礼包数据出现异常：{message}。先声明，这不代表评估设计本身有问题。"
