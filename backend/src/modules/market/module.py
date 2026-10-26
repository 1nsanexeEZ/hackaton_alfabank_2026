"""Wiring of the market module into the application."""

import asyncio
import logging

from fastapi import FastAPI

from src.core.messaging.outbox import SqlAlchemyOutboxWriter
from src.core.messaging.subscriber import Subscription
from src.core.uow import SqlAlchemyUnitOfWork
from src.modules.market.application.use_cases.key_rates import AnnounceDueKeyRatesUseCase
from src.modules.market.facade import MarketFacade
from src.modules.market.infrastructure.adapters.facade_impl import MarketFacadeImpl
from src.modules.market.infrastructure.exception_handler import register_exception_handlers
from src.modules.market.infrastructure.repositories.key_rates import SqlAlchemyKeyRateRepository
from src.modules.market.presentation.api import router
from src.modules.market.presentation.dependencies import PRODUCER

NAME = "market"
# A rate entered ahead goes out on its day within this time.
ANNOUNCE_INTERVAL_SECONDS = 3600

logger = logging.getLogger(__name__)


def register(app: FastAPI) -> None:
    app.include_router(router)
    register_exception_handlers(app)


def wire(app: FastAPI) -> None:
    clock = app.state.clock
    fallback = app.state.settings.key_rate
    app.state.facades.register(
        MarketFacade, lambda session: MarketFacadeImpl(session, clock, fallback)
    )


async def startup(app: FastAPI) -> None:
    """The hourly job announcing rates entered ahead — with the other background jobs."""
    if not app.state.settings.run_background_jobs:
        return
    stop = asyncio.Event()
    task = asyncio.create_task(_announce_due(app, stop), name="market-key-rate-announce")
    app.state.market_jobs = (stop, task)


async def shutdown(app: FastAPI) -> None:
    jobs = getattr(app.state, "market_jobs", None)
    if jobs is not None:
        stop, task = jobs
        stop.set()
        await task


async def announce_due_once(app: FastAPI) -> int:
    clock = app.state.clock
    async with app.state.session_factory() as session:
        return await AnnounceDueKeyRatesUseCase(
            SqlAlchemyUnitOfWork(session),
            SqlAlchemyKeyRateRepository(session),
            SqlAlchemyOutboxWriter(session, PRODUCER, clock),
            clock,
            app.state.settings.key_rate,
        ).execute()


async def _announce_due(app: FastAPI, stop: asyncio.Event) -> None:
    while True:
        try:
            if announced := await announce_due_once(app):
                logger.info("Announced %s key rates taking effect", announced)
        except Exception:
            logger.exception("Key rate announcement failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=ANNOUNCE_INTERVAL_SECONDS)
            return
        except TimeoutError:
            continue


def subscribers() -> list[Subscription]:
    """market listens to nothing: the rate changes through its API."""
    return []
