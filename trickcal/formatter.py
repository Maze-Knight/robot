"""Presentation-only formatting for Trickcal remote API models."""

from __future__ import annotations

from .models import TrickcalSummary


class TrickcalFormatter:
    @staticmethod
    def summary(summary: TrickcalSummary) -> str:
        lines = ["# 🖍️ 蜡笔板进度", ""]
        if summary.owned_characters is not None and summary.total_characters is not None:
            lines.append(f"已登记角色：{summary.owned_characters} / {summary.total_characters}")
        elif summary.owned_characters is not None:
            lines.append(f"已登记角色：{summary.owned_characters}")
        if summary.completed_nodes is not None and summary.total_nodes is not None:
            lines.append(f"已完成节点：{summary.completed_nodes} / {summary.total_nodes}")
        elif summary.completed_nodes is not None:
            lines.append(f"已完成节点：{summary.completed_nodes}")
        if summary.planned_nodes is not None:
            lines.append(f"计划节点：{summary.planned_nodes}")

        resources: list[str] = []
        if summary.gold_crayons_required is not None:
            resources.append(f"预计还需金蜡笔：{summary.gold_crayons_required:,}")
        if resources:
            lines.extend(("", *resources))
        lines.extend(("", "数据正常。至少这张表还在按规划工作。"))
        return "\n".join(lines)
