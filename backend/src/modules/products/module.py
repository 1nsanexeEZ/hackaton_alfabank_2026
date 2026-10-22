"""Wiring of the products module into the application."""

from fastapi import FastAPI

from src.core.messaging.subscriber import Subscription
from src.modules.products.api import router
from src.modules.products.facade import ProductsFacade
from src.modules.products.infrastructure.facade_impl import ProductsFacadeImpl

NAME = "products"


def register(app: FastAPI) -> None:
    app.include_router(router)


def wire(app: FastAPI) -> None:
    app.state.facades.register(
        ProductsFacade, lambda session: ProductsFacadeImpl(session, app.state.facades)
    )


def subscribers() -> list[Subscription]:
    """Products react to no events: the catalog changes only through seeds."""
    return []
