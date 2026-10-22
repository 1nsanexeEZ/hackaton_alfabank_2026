"""Wiring of the notifications module into the application."""

from fastapi import FastAPI

from src.core.messaging.subscriber import Subscription
from src.modules.notifications.api import router
from src.modules.notifications.facade import NotificationsFacade
from src.modules.notifications.infrastructure.consumer import feed_subscriptions
from src.modules.notifications.infrastructure.facade_impl import NotificationsFacadeImpl

NAME = "notifications"


def register(app: FastAPI) -> None:
    app.include_router(router)


def wire(app: FastAPI) -> None:
    facades = app.state.facades
    app.state.facades.register(
        NotificationsFacade,
        lambda session: NotificationsFacadeImpl(session, facades, app.state.clock),
    )


def subscribers() -> list[Subscription]:
    """One subscription per source topic; group ids `notifications.feed.<source>`."""
    return feed_subscriptions()
