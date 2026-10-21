"""Wiring of the identity module into the application."""

from fastapi import FastAPI

from src.core.access.dependencies import get_current_token
from src.core.messaging.subscriber import Subscription
from src.identity.api import router
from src.identity.dependencies import get_current_request_token

NAME = "identity"


def register(app: FastAPI) -> None:
    app.include_router(router)


def wire(app: FastAPI) -> None:
    """The core token port is implemented here. IdentityFacade is registered
    here too, once its implementation exists."""
    app.dependency_overrides[get_current_token] = get_current_request_token


def subscribers() -> list[Subscription]:
    return []
