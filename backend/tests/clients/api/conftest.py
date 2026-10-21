"""The real app with demo companies seeded by seed/clients.py; accounts live in
a FakeIdentityFacade (identity is another module)."""

from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from seed import clients as clients_seed
from seed.demo_data import ACCOUNTS, COMPANIES, DemoAccount
from seed.run import SeedContext
from src.clients.infrastructure.facade_impl import ClientsFacadeImpl
from src.clients.infrastructure.models import OrganizationModel
from src.core.access.permissions import Permissions
from src.core.config import Settings
from src.core.domain.clock import FrozenClock
from src.core.messaging.outbox import OutboxRecord
from src.identity.facade import AccountRefDTO, IdentityFacade
from src.main import create_app
from tests.fakes import install
from tests.fakes.identity_facade import FakeIdentityFacade
from tests.helpers import bearer, create_schema, token_for

NOW = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)
P = Permissions
CLIENT_PERMISSIONS = [
    P.ORGANIZATIONS_READ,
    P.ORGANIZATIONS_UPDATE,
    P.REQUESTS_READ,
    P.REQUESTS_CREATE,
]
CLIENT_POLICIES: dict[P | str, list[str]] = {
    p: ["org_member"] for p in (P.ORGANIZATIONS_READ, P.ORGANIZATIONS_UPDATE, P.REQUESTS_READ)
}
UNDERWRITER_PERMISSIONS = [P.ORGANIZATIONS_READ, P.REQUESTS_READ, P.DECISIONS_READ]

SMIRNOVA = "owner@romashka.test"
KUZNETSOVA = "accountant@romashka.test"
IVANOV = "ivanov@ip.test"
PETROV = "petrov@vector.test"
UNDERWRITER = "underwriter@bank.test"


def add_demo_account(identity: FakeIdentityFacade, demo: DemoAccount) -> AccountRefDTO:
    account = identity.add_account(
        email=demo.email,
        phone=demo.phone,
        role_name=demo.identity_role,
        last_name=demo.person.last_name,
        first_name=demo.person.first_name,
    )
    account = replace(account, middle_name=demo.person.middle_name)
    identity.accounts[account.id] = account
    return account


@dataclass
class Demo:
    app: FastAPI
    client: TestClient
    clock: FrozenClock
    identity: FakeIdentityFacade
    accounts: dict[str, AccountRefDTO]
    orgs: dict[str, UUID]

    def id_of(self, email: str) -> UUID:
        return self.accounts[email].id

    def as_client(self, email: str) -> dict[str, str]:
        return self.headers(CLIENT_PERMISSIONS, CLIENT_POLICIES, self.id_of(email))

    def as_underwriter(self) -> dict[str, str]:
        return self.headers(UNDERWRITER_PERMISSIONS, {}, self.id_of(UNDERWRITER))

    def as_admin(self) -> dict[str, str]:
        return self.headers([P.ADMIN], {})

    def headers(
        self,
        permissions: list[P | str],
        policies: dict[P | str, list[str]],
        subject: UUID | None = None,
    ) -> dict[str, str]:
        return bearer(token_for(self.app, permissions, policies, subject))

    def run[T](self, func: Callable[..., Awaitable[T]], *args: Any) -> T:
        return self.client.portal.call(func, *args)  # type: ignore[union-attr]

    def facade_call[T](self, call: Callable[[ClientsFacadeImpl], Awaitable[T]]) -> T:
        async def go() -> T:
            async with self.app.state.session_factory() as session:
                return await call(ClientsFacadeImpl(session, self.clock))

        return self.run(go)

    def outbox(self) -> list[OutboxRecord]:
        async def load() -> list[OutboxRecord]:
            async with self.app.state.session_factory() as session:
                stmt = select(OutboxRecord).order_by(OutboxRecord.id)
                return list((await session.scalars(stmt)).all())

        return self.run(load)


@contextmanager
def start_demo(
    settings: Settings, configure: Callable[[FastAPI], None] | None = None
) -> Iterator[Demo]:
    create_schema(settings.database_url)
    clock = FrozenClock(NOW)
    app = create_app(settings, clock=clock)
    identity = FakeIdentityFacade()
    accounts = {a.email: add_demo_account(identity, a) for a in ACCOUNTS}
    install(app, IdentityFacade, identity)
    if configure is not None:
        configure(app)
    with TestClient(app) as client:
        context = SeedContext(settings, app.state.session_factory, app.state.facades, clock)
        client.portal.call(clients_seed.seed, context)  # type: ignore[union-attr]

        async def organization_ids() -> dict[str, UUID]:
            async with app.state.session_factory() as session:
                rows = await session.execute(select(OrganizationModel.inn, OrganizationModel.id))
                by_inn = {inn: org_id for inn, org_id in rows.all()}
            return {c.code: by_inn[c.inn] for c in COMPANIES}

        orgs = client.portal.call(organization_ids)  # type: ignore[union-attr]
        yield Demo(app, client, clock, identity, accounts, orgs)


@pytest.fixture
def demo(settings: Settings) -> Iterator[Demo]:
    with start_demo(settings) as value:
        yield value
