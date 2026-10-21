"""Wiring of the projector module into the application."""

from fastapi import FastAPI

from src.core.messaging.subscriber import Subscription

NAME = "projector"


def register(app: FastAPI) -> None:
    """Include routers."""


def wire(app: FastAPI) -> None:
    """Register facade implementations, e.g.
    app.state.facades.register(ProjectorFacade, lambda session: ...)"""


def subscribers() -> list[Subscription]:
    """Kafka subscriptions; group_id is `projector.<purpose>`."""
    return []
