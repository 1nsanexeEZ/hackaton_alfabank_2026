"""Wiring of the decision module into the application."""

from fastapi import FastAPI

from src.core.messaging.subscriber import Subscription

NAME = "decision"


def register(app: FastAPI) -> None:
    """Include routers."""


def wire(app: FastAPI) -> None:
    """Register facade implementations, e.g.
    app.state.facades.register(DecisionFacade, lambda session: ...)"""


def subscribers() -> list[Subscription]:
    """Kafka subscriptions; group_id is `decision.<purpose>`."""
    return []
