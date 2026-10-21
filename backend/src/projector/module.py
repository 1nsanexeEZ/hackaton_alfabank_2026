"""Wiring of the projector module into the application."""

from fastapi import FastAPI

from src.core.messaging.subscriber import Subscription
from src.projector.facade import ProjectorFacade
from src.projector.infrastructure import consumer
from src.projector.infrastructure.facade_impl import ProjectorFacadeImpl

NAME = "projector"


def register(app: FastAPI) -> None:
    """No routers: screens read the projector through bff."""


def wire(app: FastAPI) -> None:
    app.state.facades.register(
        ProjectorFacade, lambda session: ProjectorFacadeImpl(session, app.state.clock)
    )


def subscribers() -> list[Subscription]:
    """One consumer group per topic: `projector.read-models.<topic>`."""
    return consumer.subscriptions()
