"""Wiring of the clients module into the application."""

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.access.organizations import MemberOrganizationsResolver
from src.core.messaging.subscriber import Subscription
from src.modules.clients.api import router
from src.modules.clients.facade import ClientsFacade
from src.modules.clients.infrastructure.facade_impl import ClientsFacadeImpl

NAME = "clients"


def register(app: FastAPI) -> None:
    app.include_router(router)


def wire(app: FastAPI) -> None:
    """ClientsFacade for the other modules and the port of the `org_member`
    policy: one implementation under both keys."""

    def facade(session: AsyncSession) -> ClientsFacadeImpl:
        # The clock is read per call: tests may swap app.state.clock.
        return ClientsFacadeImpl(session, app.state.clock)

    app.state.facades.register(ClientsFacade, facade)
    app.state.facades.register(MemberOrganizationsResolver, facade)


def subscribers() -> list[Subscription]:
    """Kafka subscriptions; group_id is `clients.<purpose>`."""
    return []
