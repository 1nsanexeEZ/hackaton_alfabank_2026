"""Wiring of the process module into the application."""

from fastapi import FastAPI

from src.core.messaging.subscriber import Subscription
from src.process.infrastructure.catalog import load_workflows

NAME = "process"


def register(app: FastAPI) -> None:
    """Include routers."""


def wire(app: FastAPI) -> None:
    # Routes are checked here: a broken BPMN file stops the application start.
    app.state.workflows = load_workflows()


def subscribers() -> list[Subscription]:
    """Kafka subscriptions; group_id is `process.<purpose>`."""
    return []
