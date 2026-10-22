"""Wiring of the process module into the application."""

import asyncio

from fastapi import FastAPI

from src.core.messaging.subscriber import Subscription
from src.process.api.routes import router
from src.process.application.ports import WorkflowSource
from src.process.facade import ProcessFacade
from src.process.infrastructure.catalog import load_workflows
from src.process.infrastructure.consumers import run_timeouts, subscriptions
from src.process.infrastructure.facade_impl import ProcessFacadeImpl

NAME = "process"


def register(app: FastAPI) -> None:
    app.include_router(router)


def wire(app: FastAPI) -> None:
    # Routes are checked here: a broken BPMN file stops the application start.
    catalog = load_workflows()
    app.state.workflows = catalog
    # Module-private port for the Kafka handlers.
    app.state.facades.register(WorkflowSource, lambda _session: catalog)
    app.state.facades.register(ProcessFacade, ProcessFacadeImpl)


async def startup(app: FastAPI) -> None:
    if not app.state.settings.run_background_jobs:
        return
    stop = asyncio.Event()
    task = asyncio.create_task(
        run_timeouts(
            app.state.session_factory, app.state.facades, app.state.workflows, app.state.clock, stop
        ),
        name="process-timeouts",
    )
    app.state.process_jobs = (stop, task)


async def shutdown(app: FastAPI) -> None:
    jobs = getattr(app.state, "process_jobs", None)
    if jobs is not None:
        stop, task = jobs
        stop.set()
        await task


def subscribers() -> list[Subscription]:
    """Events of applications, replies of enrichment, scoring and decision."""
    return subscriptions()
