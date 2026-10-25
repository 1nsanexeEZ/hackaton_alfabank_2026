"""Wiring of the market module into the application."""

from fastapi import FastAPI

from src.core.messaging.subscriber import Subscription
from src.modules.market.facade import MarketFacade
from src.modules.market.infrastructure.adapters.facade_impl import MarketFacadeImpl
from src.modules.market.infrastructure.exception_handler import register_exception_handlers
from src.modules.market.presentation.api import router

NAME = "market"


def register(app: FastAPI) -> None:
    app.include_router(router)
    register_exception_handlers(app)


def wire(app: FastAPI) -> None:
    clock = app.state.clock
    fallback = app.state.settings.key_rate
    app.state.facades.register(
        MarketFacade, lambda session: MarketFacadeImpl(session, clock, fallback)
    )


def subscribers() -> list[Subscription]:
    """market listens to nothing: the rate changes through its API."""
    return []
