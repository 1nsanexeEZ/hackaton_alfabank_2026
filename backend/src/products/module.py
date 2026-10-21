"""Wiring of the products module into the application."""

from fastapi import FastAPI

from src.core.messaging.subscriber import Subscription

NAME = "products"


def register(app: FastAPI) -> None:
    """Include routers."""


def wire(app: FastAPI) -> None:
    """Register facade implementations, e.g.
    app.state.facades.register(ProductsFacade, lambda session: ...)"""


def subscribers() -> list[Subscription]:
    """Kafka subscriptions; group_id is `products.<purpose>`."""
    return []
