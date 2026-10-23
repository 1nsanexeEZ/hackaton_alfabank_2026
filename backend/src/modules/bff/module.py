"""Wiring of the bff module into the application."""

from fastapi import FastAPI

from src.core.messaging.subscriber import Subscription
from src.modules.bff.presentation.api import router

NAME = "bff"


def register(app: FastAPI) -> None:
    app.include_router(router)


def wire(app: FastAPI) -> None:
    """bff has no facade; nothing to register."""


def subscribers() -> list[Subscription]:
    """Kafka subscriptions; group_id is `bff.<purpose>`."""
    return []
