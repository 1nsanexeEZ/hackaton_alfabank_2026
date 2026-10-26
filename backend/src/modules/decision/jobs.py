"""Фоновая задача decision: ночной пакет предодобрения (RefreshExpiringPreApprovedUseCase).

Запускается в `module.startup` вместе с остальными фоновыми задачами (`RUN_BACKGROUND_JOBS`);
тесты вызывают use case напрямую или крутят цикл с короткими интервалами.
"""

from __future__ import annotations

import asyncio
import logging

from src.modules.decision.application.refresh_pre_approved import (
    RefreshExpiringPreApprovedUseCase,
)

logger = logging.getLogger(__name__)


async def run_pre_approval_refresh(
    use_case: RefreshExpiringPreApprovedUseCase,
    stop: asyncio.Event,
    *,
    interval_seconds: float,
    within_days: int,
    first_run_after_seconds: float = 0,
    wake: asyncio.Event | None = None,
) -> None:
    """Первый проход — через `first_run_after_seconds` после старта (сид успевает пересчитать
    демо-компании сам), дальше — раз в `interval_seconds` или сразу, как выставят `wake`
    (сменилась ключевая), пока не придёт `stop`."""
    delay = first_run_after_seconds
    while not await _stopped(stop, delay, wake):
        try:
            refreshed = await use_case.execute(within_days)
            if refreshed:
                logger.info("Refreshed pre-approved offers of %s organizations", refreshed)
        except Exception:
            logger.exception("Pre-approval refresh run failed")
        delay = interval_seconds


async def _stopped(stop: asyncio.Event, seconds: float, wake: asyncio.Event | None) -> bool:
    """Ждёт `seconds` секунд или `wake`; True — за это время пришла остановка."""
    waiters = [asyncio.ensure_future(stop.wait())]
    if wake is not None:
        waiters.append(asyncio.ensure_future(wake.wait()))
    try:
        await asyncio.wait(waiters, timeout=seconds, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for waiter in waiters:
            waiter.cancel()
    if wake is not None:
        wake.clear()
    return stop.is_set()
