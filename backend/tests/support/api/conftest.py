"""Support API with fake neighbours: clients (companies and members),
applications (one card of «Ромашка») and identity (names)."""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from src.core.access.organizations import MemberOrganizationsResolver
from src.core.access.permissions import Permissions
from src.core.config import Settings
from src.core.domain.clock import FrozenClock
from src.core.messaging.outbox import OutboxRecord
from src.main import create_app
from src.modules.applications.facade import ApplicationCardDTO, ApplicationsFacade
from src.modules.clients.facade import ClientsFacade
from src.modules.identity.facade import IdentityFacade
from tests.fakes import builders, install
from tests.fakes.applications_facade import FakeApplicationsFacade
from tests.fakes.clients_facade import FakeClientsFacade
from tests.fakes.identity_facade import FakeIdentityFacade
from tests.helpers import bearer, create_schema, token_for

# As the seed gives them to the roles.
CLIENT_PERMISSIONS = [Permissions.SUPPORT_READ, Permissions.SUPPORT_CREATE]
CLIENT_POLICIES = {
    Permissions.SUPPORT_READ: ["own_only"],
    Permissions.SUPPORT_CREATE: ["own_only"],
}
STAFF_PERMISSIONS = [Permissions.SUPPORT_MANAGE]


@dataclass
class World:
    client: TestClient
    clock: FrozenClock
    romashka: UUID
    vector: UUID
    card: ApplicationCardDTO
    director: UUID
    accountant: UUID
    petrov: UUID
    anna: UUID
    boris: UUID
    admin: UUID

    def as_client(self, account_id: UUID) -> dict[str, str]:
        return bearer(token_for(self.client.app, CLIENT_PERMISSIONS, CLIENT_POLICIES, account_id))  # type: ignore[arg-type]

    def as_staff(self, account_id: UUID) -> dict[str, str]:
        return bearer(token_for(self.client.app, STAFF_PERMISSIONS, {}, account_id))  # type: ignore[arg-type]

    def as_admin(self) -> dict[str, str]:
        return bearer(token_for(self.client.app, [Permissions.ADMIN], {}, self.admin))  # type: ignore[arg-type]

    # --- shortcuts ----------------------------------------------------------

    def open(self, account_id: UUID | None = None, **body: Any) -> dict[str, Any]:
        payload = {"subject": "Не вижу выписку", "text": "Загрузил выписку, её нет в заявке"}
        response = self.client.post(
            "/support/tickets",
            json=payload | body,
            headers=self.as_client(account_id or self.director),
        )
        assert response.status_code == 201, response.text
        return response.json()

    def take(self, ticket: dict[str, Any], account_id: UUID | None = None) -> dict[str, Any]:
        response = self.client.post(
            f"/support/queue/{ticket['id']}/take", headers=self.as_staff(account_id or self.anna)
        )
        assert response.status_code == 200, response.text
        return response.json()

    def outbox_types(self) -> list[str]:
        async def read() -> list[str]:
            async with self.client.app.state.session_factory() as session:  # type: ignore[attr-defined]
                rows = await session.scalars(select(OutboxRecord).order_by(OutboxRecord.id))
                return [row.message_type for row in rows]

        return self.client.portal.call(read)  # type: ignore[union-attr]


@pytest.fixture
def world(settings: Settings) -> Iterator[World]:
    clock = FrozenClock(builders.NOW)
    app = create_app(settings, clock=clock)

    clients = FakeClientsFacade()
    romashka = clients.add_organization(builders.organization_snapshot("romashka"))
    vector = clients.add_organization(builders.organization_snapshot("vector"))
    director, accountant, petrov = uuid4(), uuid4(), uuid4()
    clients.add_member(director, romashka.id, "director")
    clients.add_member(accountant, romashka.id, "employee")
    clients.add_member(petrov, vector.id, "director")

    applications = FakeApplicationsFacade()
    card = applications.add_card(builders.application_card(romashka))

    identity = FakeIdentityFacade()
    anna, boris, admin = uuid4(), uuid4(), uuid4()
    people = [
        (director, "Ромашкин", "Иван", "client"),
        (accountant, "Счётова", "Мария", "client"),
        (petrov, "Петров", "Пётр", "client"),
        (anna, "Аналитикова", "Анна", "underwriter"),
        (boris, "Борисов", "Борис", "underwriter"),
        (admin, "Админов", "Алексей", "admin"),
    ]
    for account_id, last_name, first_name, role in people:
        identity.add_account(
            account_id=account_id, last_name=last_name, first_name=first_name, role_name=role
        )

    install(app, ClientsFacade, clients)
    install(app, MemberOrganizationsResolver, clients)
    install(app, ApplicationsFacade, applications)
    install(app, IdentityFacade, identity)

    create_schema(settings.database_url)
    with TestClient(app) as client:
        yield World(
            client=client,
            clock=clock,
            romashka=romashka.id,
            vector=vector.id,
            card=card,
            director=director,
            accountant=accountant,
            petrov=petrov,
            anna=anna,
            boris=boris,
            admin=admin,
        )
