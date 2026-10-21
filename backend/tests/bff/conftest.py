"""BFF API with every neighbour faked: ООО «Ромашка» (director, accountant,
employee), ИП Иванов (the same accountant), ООО «Вектор» (Petrov), a newcomer
without companies and an underwriter. Tokens are built from the seeded roles."""

from collections.abc import Callable, Iterator
from contextlib import ExitStack
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from seed.identity import ROLES
from src.applications.facade import ApplicationCardDTO, ApplicationsFacade
from src.clients.facade import ClientsFacade, OrganizationSnapshotDTO
from src.core.access.organizations import MemberOrganizationsResolver
from src.core.access.permissions import Permissions
from src.core.config import Settings
from src.core.domain.clock import FrozenClock
from src.core.facades import FacadeNotRegisteredError
from src.decision.facade import DecisionFacade
from src.enrichment.facade import EnrichmentFacade
from src.main import create_app
from src.notifications.facade import NotificationsFacade
from src.process.facade import ProcessFacade
from src.products.facade import ProductsFacade
from src.projector.facade import ProjectorFacade
from src.scoring.facade import ScoringFacade
from tests.bff import factories
from tests.fakes import builders, install
from tests.fakes.applications_facade import FakeApplicationsFacade
from tests.fakes.clients_facade import FakeClientsFacade
from tests.fakes.decision_facade import FakeDecisionFacade
from tests.fakes.enrichment_facade import FakeEnrichmentFacade
from tests.fakes.notifications_facade import FakeNotificationsFacade
from tests.fakes.process_facade import FakeProcessFacade
from tests.fakes.products_facade import FakeProductsFacade
from tests.fakes.projector_facade import FakeProjectorFacade
from tests.fakes.scoring_facade import FakeScoringFacade
from tests.helpers import bearer, create_schema, token_for

ROLE_SPECS = {role.name: role for role in ROLES}


@dataclass
class World:
    client: TestClient
    clients: FakeClientsFacade
    applications: FakeApplicationsFacade
    projector: FakeProjectorFacade
    decision: FakeDecisionFacade
    notifications: FakeNotificationsFacade
    products: FakeProductsFacade
    enrichment: FakeEnrichmentFacade
    scoring: FakeScoringFacade
    process: FakeProcessFacade
    romashka: OrganizationSnapshotDTO
    ivanov: OrganizationSnapshotDTO
    vector: OrganizationSnapshotDTO
    director: UUID
    accountant: UUID
    employee: UUID
    petrov: UUID
    newcomer: UUID

    def token(
        self,
        role: str,
        account_id: UUID | None = None,
        without: tuple[Permissions, ...] = (),
    ) -> dict[str, str]:
        spec = ROLE_SPECS[role]
        permissions = [p for p in spec.permissions if p not in without]
        policies: dict[Permissions | str, list[str]] = {
            k: [str(p) for p in v] for k, v in spec.policies.items()
        }
        app = self.client.app
        return bearer(token_for(app, permissions, policies, account_id or uuid4()))  # type: ignore[arg-type]

    def as_client(self, account_id: UUID) -> dict[str, str]:
        return self.token("client", account_id)

    def as_underwriter(self, without: tuple[Permissions, ...] = ()) -> dict[str, str]:
        return self.token("underwriter", without=without)

    def get(self, path: str, headers: dict[str, str], **params: Any) -> httpx.Response:
        return self.client.get(path, headers=headers, params=params)

    def add_application(
        self, organization: OrganizationSnapshotDTO | None = None, **overrides: Any
    ) -> ApplicationCardDTO:
        """The card in applications and its row in the projector."""
        overrides.setdefault("applicant_account_id", self.director)
        card = builders.application_card(organization or self.romashka, **overrides)
        self.applications.add_card(card)
        self.projector.add_overview(factories.overview(card))
        return card


ALL_FACADES: tuple[type[Any], ...] = (
    ClientsFacade,
    MemberOrganizationsResolver,
    ApplicationsFacade,
    ProjectorFacade,
    DecisionFacade,
    NotificationsFacade,
    ProductsFacade,
    EnrichmentFacade,
    ScoringFacade,
    ProcessFacade,
)


def not_wired(key: type[Any]) -> Callable[[Any], Any]:
    def factory(_session: Any) -> Any:
        raise FacadeNotRegisteredError(f"Facade {key.__name__} is not registered")

    return factory


@pytest.fixture
def make_world(settings: Settings) -> Iterator[Callable[..., World]]:
    """`make_world(skip=(DecisionFacade,))` — the app as it runs while the
    owner of a facade has not wired it yet (whatever its module.wire does)."""
    create_schema(settings.database_url)
    with ExitStack() as stack:

        def make(skip: tuple[type[Any], ...] = ()) -> World:
            app = create_app(settings, clock=FrozenClock(builders.NOW))
            clients = FakeClientsFacade()
            romashka = clients.add_organization(builders.organization_snapshot("romashka"))
            ivanov = clients.add_organization(builders.organization_snapshot("ivanov"))
            vector = clients.add_organization(builders.organization_snapshot("vector"))
            director, accountant, employee, petrov = uuid4(), uuid4(), uuid4(), uuid4()
            clients.add_member(director, romashka.id, "director")
            clients.add_member(accountant, romashka.id, "accountant")
            clients.add_member(employee, romashka.id, "employee")
            clients.add_member(accountant, ivanov.id, "accountant")
            clients.add_member(petrov, vector.id, "director")

            products = FakeProductsFacade()
            products.add_product(builders.product("UNSECURED", name="Кредит без залога"))
            products.add_product(builders.product("OVERDRAFT", name="Овердрафт"))

            fakes: dict[type[Any], Any] = {
                ClientsFacade: clients,
                MemberOrganizationsResolver: clients,
                ApplicationsFacade: FakeApplicationsFacade(),
                ProjectorFacade: FakeProjectorFacade(),
                DecisionFacade: FakeDecisionFacade(),
                NotificationsFacade: FakeNotificationsFacade(),
                ProductsFacade: products,
                EnrichmentFacade: FakeEnrichmentFacade(),
                ScoringFacade: FakeScoringFacade(),
                ProcessFacade: FakeProcessFacade(),
            }
            for key, fake in fakes.items():
                if key in skip:
                    app.state.facades.register(key, not_wired(key))
                else:
                    install(app, key, fake)
            client = stack.enter_context(TestClient(app))
            return World(
                client=client,
                clients=clients,
                applications=fakes[ApplicationsFacade],
                projector=fakes[ProjectorFacade],
                decision=fakes[DecisionFacade],
                notifications=fakes[NotificationsFacade],
                products=products,
                enrichment=fakes[EnrichmentFacade],
                scoring=fakes[ScoringFacade],
                process=fakes[ProcessFacade],
                romashka=romashka,
                ivanov=ivanov,
                vector=vector,
                director=director,
                accountant=accountant,
                employee=employee,
                petrov=petrov,
                newcomer=uuid4(),
            )

        yield make


@pytest.fixture
def world(make_world: Callable[..., World]) -> World:
    return make_world()
