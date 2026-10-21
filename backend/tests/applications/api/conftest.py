"""Applications API with fake neighbours: clients (companies and rights),
products (catalog), identity (step-up password) and an in-memory bucket."""

from collections.abc import Awaitable, Callable, Iterator
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from src.applications.domain.application import CreditApplication
from src.applications.infrastructure.repository import SqlAlchemyApplicationRepository
from src.clients.facade import ClientsFacade
from src.core.access.organizations import MemberOrganizationsResolver
from src.core.access.permissions import Permissions
from src.core.config import Settings
from src.core.domain.clock import FrozenClock
from src.core.messaging.outbox import OutboxRecord
from src.identity.facade import IdentityFacade
from src.main import create_app
from src.products.facade import ProductsFacade, RequiredDocumentDTO
from tests.fakes import builders, install
from tests.fakes.clients_facade import FakeClientsFacade
from tests.fakes.document_storage import FakeDocumentStorage
from tests.fakes.identity_facade import FakeIdentityFacade
from tests.fakes.products_facade import FakeProductsFacade
from tests.helpers import bearer, create_schema, token_for

PASSWORD = "Sign-password-1"
CLIENT_PERMISSIONS = [
    Permissions.REQUESTS_READ,
    Permissions.REQUESTS_CREATE,
    Permissions.REQUESTS_UPDATE,
    Permissions.ORGANIZATIONS_READ,
]
CLIENT_POLICIES = {
    Permissions.REQUESTS_READ: ["org_member"],
    Permissions.REQUESTS_CREATE: ["org_member"],
    Permissions.REQUESTS_UPDATE: ["org_member"],
}


@dataclass
class World:
    client: TestClient
    clock: FrozenClock
    clients: FakeClientsFacade
    products: FakeProductsFacade
    identity: FakeIdentityFacade
    storage: FakeDocumentStorage
    romashka: UUID
    vector: UUID
    director: UUID
    accountant: UUID
    employee: UUID
    petrov: UUID

    def headers(self, account_id: UUID) -> dict[str, str]:
        token = token_for(self.client.app, CLIENT_PERMISSIONS, CLIENT_POLICIES, account_id)  # type: ignore[arg-type]
        return bearer(token)

    def underwriter(self) -> dict[str, str]:
        token = token_for(self.client.app, [Permissions.REQUESTS_READ], {}, uuid4())  # type: ignore[arg-type]
        return bearer(token)

    def run(self, fn: Callable[..., Awaitable[Any]], *args: Any) -> Any:
        return self.client.portal.call(fn, *args)  # type: ignore[union-attr]

    def process(self, application_id: str, step: Callable[[CreditApplication], None]) -> None:
        """Play the process engine: change the aggregate directly (commands come in #23)."""

        async def change() -> None:
            async with self.client.app.state.session_factory() as session:  # type: ignore[attr-defined]
                repository = SqlAlchemyApplicationRepository(session)
                application = await repository.get(UUID(application_id))
                step(application)
                application.pull_events()
                await repository.save(application)
                await session.commit()

        self.run(change)

    def outbox_types(self) -> list[str]:
        async def read() -> list[str]:
            async with self.client.app.state.session_factory() as session:  # type: ignore[attr-defined]
                rows = await session.scalars(select(OutboxRecord).order_by(OutboxRecord.id))
                return [row.message_type for row in rows]

        return self.run(read)

    # --- shortcuts ----------------------------------------------------------

    def create(self, account_id: UUID | None = None, product_code: str = "UNSECURED") -> dict:
        response = self.client.post(
            "/applications",
            json={"organization_id": str(self.romashka), "product_code": product_code},
            headers=self.headers(account_id or self.director),
        )
        assert response.status_code == 201, response.text
        return response.json()

    def upload(self, application: dict, document_type: str = "bank_statement", **kw: Any) -> dict:
        content: bytes = kw.get("content", b"date;amount\n2026-01-05;150000.00\n")
        content_type: str = kw.get("content_type", "text/csv")
        headers = self.headers(kw.get("account_id", self.director))
        announced = self.client.post(
            f"/applications/{application['id']}/documents",
            json={
                "type": document_type,
                "filename": "statement.csv",
                "content_type": content_type,
                "size_bytes": len(content),
            },
            headers=headers,
        )
        assert announced.status_code == 201, announced.text
        document = announced.json()["document"]
        key = f"applications/{application['id']}/{document['id']}"
        self.storage.put(key, content, kw.get("stored_type", content_type))
        confirmed = self.client.post(
            f"/applications/{application['id']}/documents/{document['id']}/confirm",
            headers=headers,
        )
        assert confirmed.status_code == 200, confirmed.text
        return confirmed.json()

    def ready(self, account_id: UUID | None = None) -> dict:
        """Draft that can be submitted."""
        application = self.create(account_id)
        self.upload(application, account_id=account_id or self.director)
        response = self.client.patch(
            f"/applications/{application['id']}",
            json={
                "version": self.client.get(
                    f"/applications/{application['id']}", headers=self.headers(self.director)
                ).json()["version"],
                "request": {"amount": "3000000", "term_months": 24, "purpose": "working_capital"},
                "consents": {"personal_data": True, "credit_bureau": True},
            },
            headers=self.headers(account_id or self.director),
        )
        assert response.status_code == 200, response.text
        return response.json()

    def submit(self, application: dict, account_id: UUID | None = None) -> dict:
        response = self.client.post(
            f"/applications/{application['id']}/submit",
            headers=self.headers(account_id or self.director),
        )
        assert response.status_code == 200, response.text
        return response.json()


@pytest.fixture
def world(settings: Settings) -> Iterator[World]:
    clock = FrozenClock()
    app = create_app(settings, clock=clock)

    clients = FakeClientsFacade()
    romashka = clients.add_organization(builders.organization_snapshot("romashka")).id
    vector = clients.add_organization(builders.organization_snapshot("vector")).id
    director, accountant, employee, petrov = uuid4(), uuid4(), uuid4(), uuid4()
    clients.add_member(director, romashka, "director")
    clients.add_member(accountant, romashka, "accountant")
    clients.add_member(employee, romashka, "employee")
    clients.add_member(petrov, vector, "director")

    products = FakeProductsFacade()
    products.add_product(
        builders.product(
            "UNSECURED",
            required_documents=(RequiredDocumentDTO("bank_statement", "Выписка по счёту"),),
        )
    )
    products.add_product(builders.product("OVERDRAFT"))

    identity = FakeIdentityFacade()
    for account_id in (director, accountant, employee, petrov):
        identity.add_account(account_id=account_id, password=PASSWORD)

    storage = FakeDocumentStorage()
    install(app, ClientsFacade, clients)
    install(app, MemberOrganizationsResolver, clients)
    install(app, ProductsFacade, products)
    install(app, IdentityFacade, identity)
    app.state.document_storage = storage

    create_schema(settings.database_url)
    with TestClient(app) as client:
        yield World(
            client,
            clock,
            clients,
            products,
            identity,
            storage,
            romashka,
            vector,
            director,
            accountant,
            employee,
            petrov,
        )
