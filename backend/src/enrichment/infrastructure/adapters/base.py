"""Базовый HTTP-адаптер: таймаут, ретраи с экспоненциальной задержкой на 5xx и
таймауты, перевод HTTP-ошибок в доменные SourceNotFound/SourceUnavailable.

Весь «чужой» формат остаётся в адаптерах; домен о нём не знает.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from decimal import Decimal
from typing import Any

import httpx

from src.enrichment.application.ports import SourceNotFound, SourceUnavailable


def kop_to_rub(kopecks: int) -> Decimal:
    return Decimal(int(kopecks)) / 100


class HttpSource:
    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        backoff: Sequence[float] = (0.5, 1.0, 2.0),
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._client = client
        self._backoff = tuple(backoff)
        self._sleep = sleep

    async def _request(self, method: str, path: str, json: dict[str, Any] | None = None) -> Any:
        attempt = 0
        while True:
            try:
                response = await self._client.request(method, path, json=json)
            except httpx.TimeoutException as exc:
                if attempt < len(self._backoff):
                    await self._sleep(self._backoff[attempt])
                    attempt += 1
                    continue
                raise SourceUnavailable(
                    "timeout", "таймаут источника", attempts=attempt + 1
                ) from exc
            except httpx.HTTPError as exc:
                if attempt < len(self._backoff):
                    await self._sleep(self._backoff[attempt])
                    attempt += 1
                    continue
                raise SourceUnavailable(
                    "unavailable", f"ошибка соединения: {exc}", attempts=attempt + 1
                ) from exc

            if response.status_code == 404:
                raise SourceNotFound(attempts=attempt + 1)
            if response.status_code >= 500:
                if attempt < len(self._backoff):
                    await self._sleep(self._backoff[attempt])
                    attempt += 1
                    continue
                raise SourceUnavailable(
                    "unavailable", f"HTTP {response.status_code}", attempts=attempt + 1
                )
            if response.status_code >= 400:
                raise SourceUnavailable(
                    "bad_response", f"HTTP {response.status_code}", attempts=attempt + 1
                )
            try:
                return response.json()
            except ValueError as exc:
                raise SourceUnavailable(
                    "bad_response", "некорректный JSON источника", attempts=attempt + 1
                ) from exc
