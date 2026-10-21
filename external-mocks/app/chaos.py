"""Chaos-middleware: задержки и случайные 503, чтобы адаптеры в бэкенде ловили таймауты и ретраи.

В тестах отключается (MOCK_FAILURE_RATE=0, нулевые задержки). `/health` не трогаем —
по нему Docker healthcheck.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse

from app.config import get_settings

SAFE_PATHS = frozenset({"/health"})


async def chaos_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    if request.url.path in SAFE_PATHS:
        return await call_next(request)
    settings = get_settings()
    low = min(settings.latency_ms_min, settings.latency_ms_max)
    high = max(settings.latency_ms_min, settings.latency_ms_max)
    if high > 0:
        await asyncio.sleep(random.uniform(low, high) / 1000)
    if settings.failure_rate > 0 and random.random() < settings.failure_rate:
        return JSONResponse(
            status_code=503,
            content={"detail": "Источник временно недоступен", "simulated": True},
        )
    return await call_next(request)
