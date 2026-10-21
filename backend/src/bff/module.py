"""Wiring of the bff module into the application."""

from fastapi import FastAPI

from src.core.messaging.subscriber import Subscription

NAME = "bff"


def register(app: FastAPI) -> None:
    """Include routers."""


def wire(app: FastAPI) -> None:
    """bff has no facade; nothing to register."""


def subscribers() -> list[Subscription]:
    """Kafka subscriptions; group_id is `bff.<purpose>`."""
    return []
