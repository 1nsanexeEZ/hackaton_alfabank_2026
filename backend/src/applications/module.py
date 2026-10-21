"""Wiring of the applications module into the application."""

from fastapi import FastAPI

from src.core.messaging.subscriber import Subscription

NAME = "applications"


def register(app: FastAPI) -> None:
    """Include routers."""


def wire(app: FastAPI) -> None:
    """Register facade implementations, e.g.
    app.state.facades.register(ApplicationsFacade, lambda session: ...)"""


def subscribers() -> list[Subscription]:
    """Kafka subscriptions; group_id is `applications.<purpose>`."""
    return []
