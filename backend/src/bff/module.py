"""Wiring of the bff module into the application."""

from fastapi import FastAPI

from src.bff.api import backoffice, client
from src.core.messaging.subscriber import Subscription

NAME = "bff"


def register(app: FastAPI) -> None:
    app.include_router(client.router)
    app.include_router(backoffice.router)


def wire(app: FastAPI) -> None:
    """bff has no facade; nothing to register."""


def subscribers() -> list[Subscription]:
    """Kafka subscriptions; group_id is `bff.<purpose>`."""
    return []
