"""Wiring of the scoring module into the application."""

from fastapi import FastAPI

from src.core.messaging.subscriber import Subscription

NAME = "scoring"


def register(app: FastAPI) -> None:
    """Include routers."""


def wire(app: FastAPI) -> None:
    """Register facade implementations, e.g.
    app.state.facades.register(ScoringFacade, lambda session: ...)"""


def subscribers() -> list[Subscription]:
    """Kafka subscriptions; group_id is `scoring.<purpose>`."""
    return []
