"""Wiring of the products module into the application."""

from fastapi import FastAPI

from src.core.messaging.subscriber import Subscription
from src.modules.products.api import router
from src.modules.products.application.services import rate_shift_of
from src.modules.products.facade import ProductsFacade
from src.modules.products.infrastructure.facade_impl import ProductsFacadeImpl

NAME = "products"


def register(app: FastAPI) -> None:
    app.include_router(router)


def wire(app: FastAPI) -> None:
    shift = rate_shift_of(app.state.settings)
    app.state.facades.register(
        ProductsFacade, lambda session: ProductsFacadeImpl(session, app.state.facades, shift)
    )


def subscribers() -> list[Subscription]:
    """Products react to no events: the catalog changes through its API and seeds."""
    return []
