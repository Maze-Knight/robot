from __future__ import annotations

import re
import math
from dataclasses import dataclass

from . import copywriting as copy
from .client import GiftApiClient
from .models import GiftPeriod, RatingRule


@dataclass(frozen=True, slots=True)
class GiftView:
    content: str
    periods: tuple[GiftPeriod, ...] = ()
    period_page: int = 1
    period_total_pages: int = 1


class GiftQueryService:
    def __init__(self, client: GiftApiClient) -> None:
        self.client = client

    @staticmethod
    def _period_number(name: str) -> int:
        matched = re.search(
            r"第\s*([\d零〇一二两三四五六七八九十百]+)\s*期|"
            r"(?<!\d)(\d+)\s*期",
            name,
        )
        if not matched:
            return -1
        value = matched.group(1) or matched.group(2)
        if value.isdigit():
            return int(value)
        digits = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3,
                  "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
        total = 0
        current = 0
        for character in value:
            if character in digits:
                current = digits[character]
            elif character == "十":
                total += (current or 1) * 10
                current = 0
            elif character == "百":
                total += (current or 1) * 100
                current = 0
        return total + current

    def order_periods(self, periods: list[GiftPeriod]) -> list[GiftPeriod]:
        return sorted(
            periods,
            key=lambda period: (
                self._period_number(period.name),
                period.created_timestamp,
                period.sort_order,
            ),
            reverse=True,
        )

    async def _periods(self) -> list[GiftPeriod]:
        return self.order_periods(await self.client.list_periods())

    async def _rules(self) -> dict[str, RatingRule]:
        try:
            rules = await self.client.list_rating_rules()
        except Exception:
            # Gift rows already carry a rating code; a missing optional label
            # endpoint must not prevent the actual value query.
            return {}
        return {rule.code: rule for rule in rules}

    async def home(self) -> GiftView:
        periods = await self._periods()
        return GiftView(copy.home(periods[0] if periods else None, len(periods)))

    async def periods(self, page: int = 1, *, page_size: int = 8) -> GiftView:
        all_periods = await self._periods()
        total_pages = max(1, math.ceil(len(all_periods) / page_size))
        safe_page = max(1, min(page, total_pages))
        start = (safe_page - 1) * page_size
        periods = all_periods[start : start + page_size]
        return GiftView(
            copy.period_list(periods, safe_page, total_pages),
            tuple(periods),
            safe_page,
            total_pages,
        )

    async def ranking(self, period_query: str = "") -> GiftView:
        periods = await self._periods()
        period = self._find_period(periods, period_query)
        if period is None:
            query = period_query or "最新一期"
            return GiftView(f"# 🎁 {query}\n\n没有找到这个期次。先查看“选择期次”。")
        gifts = await self.client.list_gifts(folder_id=period.id)
        return GiftView(copy.ranking(period, gifts, await self._rules()))

    async def search(self, keyword: str) -> GiftView:
        gifts = await self.client.list_gifts(search=keyword)
        return GiftView(copy.search_results(keyword, gifts, await self._rules()))

    @staticmethod
    def _find_period(
        periods: list[GiftPeriod], query: str
    ) -> GiftPeriod | None:
        if not periods:
            return None
        normalized = query.strip().casefold()
        if not normalized or normalized in {"最新", "最新一期", "当期"}:
            return periods[0]
        exact = next(
            (period for period in periods if period.name.casefold() == normalized),
            None,
        )
        if exact:
            return exact
        matches = [period for period in periods if normalized in period.name.casefold()]
        return matches[0] if len(matches) == 1 else None
