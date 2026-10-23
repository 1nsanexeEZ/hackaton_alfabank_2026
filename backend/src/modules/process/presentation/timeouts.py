"""The background job of the engine: processes stuck waiting for a reply go
down their timeout branch (TimeOutStuckStepsUseCase)."""

import asyncio
import logging
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.domain.clock import Clock
from src.core.facades import FacadeRegistry
from src.modules.process.presentation.dependencies import time_out_stuck_steps_use_case

logger = logging.getLogger(__name__)


async def time_out_stuck_steps(
    session_factory: async_sessionmaker[AsyncSession],
    facades: FacadeRegistry,
    clock: Clock,
    min_wait: timedelta = timedelta(seconds=30),
    batch_size: int = 100,
) -> int:
    """Processes waiting for a reply too long: one transaction per application."""
    use_case = time_out_stuck_steps_use_case(session_factory, facades, clock)
    return await use_case.execute(min_wait, batch_size)


async def run_timeouts(
    session_factory: async_sessionmaker[AsyncSession],
    facades: FacadeRegistry,
    clock: Clock,
    stop: asyncio.Event,
    interval_seconds: float = 30,
) -> None:
    while not stop.is_set():
        try:
            count = await time_out_stuck_steps(session_factory, facades, clock)
            if count:
                logger.warning("%s process steps timed out", count)
        except Exception:
            logger.exception("Process timeout run failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval_seconds)
        except TimeoutError:
            pass
