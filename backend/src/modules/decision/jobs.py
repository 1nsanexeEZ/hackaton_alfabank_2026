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
) -> None:
    """Первый проход — через `first_run_after_seconds` после старта (сид успевает пересчитать
    демо-компании сам), дальше — раз в `interval_seconds`, пока не придёт `stop`."""
    delay = first_run_after_seconds
    while not await _stopped(stop, delay):
        try:
            refreshed = await use_case.execute(within_days)
            if refreshed:
                logger.info("Refreshed pre-approved offers of %s organizations", refreshed)
        except Exception:
            logger.exception("Pre-approval refresh run failed")
        delay = interval_seconds


async def _stopped(stop: asyncio.Event, seconds: float) -> bool:
    """Ждёт `seconds` секунд; True — за это время пришла остановка."""
    try:
        await asyncio.wait_for(stop.wait(), timeout=seconds)
    except TimeoutError:
        return False
    return True
