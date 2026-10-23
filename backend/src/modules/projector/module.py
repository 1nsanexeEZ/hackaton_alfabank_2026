"""Wiring of the projector module into the application."""

from fastapi import FastAPI

from src.core.messaging.subscriber import Subscription
from src.modules.projector.facade import ProjectorFacade
from src.modules.projector.presentation import consumers
from src.modules.projector.presentation.dependencies import projector_facade

NAME = "projector"


def register(app: FastAPI) -> None:
    """No routers: screens read the projector through bff."""


def wire(app: FastAPI) -> None:
    app.state.facades.register(
        ProjectorFacade, lambda session: projector_facade(session, app.state.clock)
    )


def subscribers() -> list[Subscription]:
    """One consumer group per topic: `projector.read-models.<topic>`."""
    return consumers.subscriptions()
