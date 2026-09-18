"""Short, in-character copy for the Trickcal board entry points."""

HOME = """# 🖍️ 嘟嘟脸蜡笔板

角色、节点和资源都记在这里。

靠记忆管理这种东西，效率太低了。"""

FIRST_ENTRY = """🖍️ 蜡笔板入口已经准备好了。

身份也确认过了，直接进去就行。"""

EMPTY = """你的蜡笔板还是空的。

先打开一次终端，本市长会替你把档案建好。"""

ENTRY_FAILED = """入口没生成出来。

……理论上不该这样。再试一次。"""

UNAVAILABLE = """蜡笔板终端暂时还没接入市政网络。

施工还没结束。"""

TOO_FAST = """指令堆得太快了。

等两秒，系统不会因为催促就变快。"""

CATALOG_STALE = "目录更新出了点问题。旧数据还能用，别急着宣布市政系统停摆。"


def legacy_summary_text(summary: dict[str, int]) -> str:
    """Legacy/local display kept only for TRICKCAL_MODE=local rollback."""
    return "\n".join(
        (
            "# 🖍️ 蜡笔板进度",
            "",
            f"已登记角色：{summary['owned_units']} / {summary['total_units']}",
            f"已完成节点：{summary['selected_nodes']} / {summary['total_nodes']}",
            f"计划节点：{summary['planned_nodes']}",
            "",
            "预计还需：",
            f"金币：{summary['remaining_gold']:,}",
            f"金蜡笔：{summary['remaining_gold_crayons']:,}",
            "",
            "数据正常。至少这张表没有擅自长出新节点。",
        )
    )
