from __future__ import annotations

from typing import Any

import httpx

from .models import Gift, GiftPeriod, RatingRule


class GiftApiError(RuntimeError):
    """A safe, user-displayable failure from the gift website API."""


class GiftApiClient:
    def __init__(
        self,
        http_client: httpx.AsyncClient,
        api_base_url: str,
        *,
        timeout: float = 15.0,
    ) -> None:
        self._http = http_client
        self._base = api_base_url.rstrip("/")
        self._timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self._base)

    async def _get(
        self, path: str, *, params: dict[str, str] | None = None
    ) -> dict[str, Any]:
        if not self.configured:
            raise GiftApiError("礼包数据源尚未配置")
        try:
            response = await self._http.get(
                f"{self._base}{path}", params=params, timeout=self._timeout
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.TimeoutException as exc:
            raise GiftApiError("礼包数据库响应超时") from exc
        except httpx.HTTPStatusError as exc:
            raise GiftApiError(f"礼包网站接口返回 HTTP {exc.response.status_code}") from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise GiftApiError("礼包网站暂时无法访问") from exc
        if not isinstance(payload, dict) or not payload.get("success"):
            raise GiftApiError("礼包网站返回了无法识别的数据")
        return payload

    async def list_periods(self) -> list[GiftPeriod]:
        payload = await self._get("/api/gift-folders")
        rows = payload.get("data", [])
        if not isinstance(rows, list):
            raise GiftApiError("礼包期次数据格式异常")
        periods = [
            GiftPeriod.from_api(row)
            for row in rows
            if isinstance(row, dict)
            and bool(row.get("is_enabled", True))
            and int(row.get("gift_count", 0) or 0) > 0
        ]
        return periods

    async def list_gifts(
        self, *, folder_id: str | None = None, search: str | None = None
    ) -> list[Gift]:
        params = {
            "page": "1",
            "pageSize": "100" if folder_id else "20",
            "includeSpecial": "true",
            "sortBy": "cost_performance",
            "sortOrder": "desc",
        }
        if folder_id:
            params["folderId"] = folder_id
        if search:
            params["search"] = search
        payload = await self._get("/api/gifts", params=params)
        rows = payload.get("data", [])
        if not isinstance(rows, list):
            raise GiftApiError("礼包列表数据格式异常")
        return [Gift.from_api(row) for row in rows if isinstance(row, dict)]

    async def list_rating_rules(self) -> list[RatingRule]:
        payload = await self._get("/api/ratings/enabled")
        rows = payload.get("data", [])
        if not isinstance(rows, list):
            return []
        return sorted(
            (RatingRule.from_api(row) for row in rows if isinstance(row, dict)),
            key=lambda rule: rule.sort_order,
        )
