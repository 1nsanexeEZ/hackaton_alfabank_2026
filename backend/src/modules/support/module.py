"""Wiring of the support module into the application."""

from fastapi import FastAPI

from src.core.messaging.subscriber import Subscription
from src.modules.support.presentation.api import router

NAME = "support"


def register(app: FastAPI) -> None:
    app.include_router(router)


def wire(app: FastAPI) -> None:
    """support has no facade; nothing to register."""


def subscribers() -> list[Subscription]:
    """support listens to nothing: its events go to support.events for the feed."""
    return []
