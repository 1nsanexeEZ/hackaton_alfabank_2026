"""Wiring of the identity module into the application."""

from fastapi import FastAPI

from src.core.access.dependencies import get_current_token
from src.core.messaging.subscriber import Subscription
from src.modules.identity.api import router
from src.modules.identity.dependencies import get_current_request_token
from src.modules.identity.facade import IdentityFacade
from src.modules.identity.facade_impl import IdentityFacadeImpl

NAME = "identity"


def register(app: FastAPI) -> None:
    app.include_router(router)


def wire(app: FastAPI) -> None:
    """The core token port and IdentityFacade are implemented here."""
    app.dependency_overrides[get_current_token] = get_current_request_token
    # The hasher is created on startup (lifespan), so it's read when a facade is built.
    app.state.facades.register(
        IdentityFacade, lambda session: IdentityFacadeImpl(session, app.state.password_hasher)
    )


def subscribers() -> list[Subscription]:
    return []
