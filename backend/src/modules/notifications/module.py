"""Wiring of the notifications module into the application."""

from fastapi import FastAPI

from src.core.messaging.subscriber import Subscription
from src.modules.notifications.facade import NotificationsFacade
from src.modules.notifications.presentation.api import router
from src.modules.notifications.presentation.consumers import feed_subscriptions
from src.modules.notifications.presentation.dependencies import notifications_facade

NAME = "notifications"


def register(app: FastAPI) -> None:
    app.include_router(router)


def wire(app: FastAPI) -> None:
    facades = app.state.facades
    app.state.facades.register(
        NotificationsFacade,
        lambda session: notifications_facade(session, facades, app.state.clock),
    )


def subscribers() -> list[Subscription]:
    """One subscription per source topic; group ids `notifications.feed.<source>`."""
    return feed_subscriptions()
