"""The background job of the module: overdue offers go to EXPIRED
(ExpireOffersUseCase)."""

import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.domain.clock import Clock
from src.modules.applications.presentation.dependencies import expire_offers_use_case

logger = logging.getLogger(__name__)


async def expire_offers(
    session_factory: async_sessionmaker[AsyncSession], clock: Clock, batch_size: int = 100
) -> int:
    """Move overdue offers to EXPIRED, one transaction per application."""
    return await expire_offers_use_case(session_factory, clock).execute(batch_size)


async def run_offer_expiry(
    session_factory: async_sessionmaker[AsyncSession],
    clock: Clock,
    stop: asyncio.Event,
    interval_seconds: float,
) -> None:
    while not stop.is_set():
        try:
            expired = await expire_offers(session_factory, clock)
            if expired:
                logger.info("Expired %s offers", expired)
        except Exception:
            logger.exception("Offer expiry run failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval_seconds)
        except TimeoutError:
            pass
