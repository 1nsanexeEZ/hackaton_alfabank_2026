"""FetchEnrichment carries the head by the registry and their own consent (218-FZ):
the company's consent in the application does not cover a person's credit history. Who
submitted the application, when not the head, goes as a representative for the 115-FZ check."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from src.core.messaging.contracts.enrichment import FetchEnrichment, PersonRef
from src.modules.process.application.mappers.messages import command_contract
from src.modules.process.domain.enums import NodeType
from src.modules.process.domain.steps import STEPS, PersonFact, StepInput
from src.modules.process.domain.workflow import Node, NodeConfig
from src.modules.process.infrastructure.adapters.application_facts import ApplicationFacts
from tests.fakes import builders
from tests.fakes.applications_facade import FakeApplicationsFacade
from tests.fakes.clients_facade import FakeClientsFacade
from tests.fakes.identity_facade import FakeIdentityFacade
from tests.process.unit.routes import context

NOW = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)


class World:
    def __init__(self) -> None:
        self.applications = FakeApplicationsFacade()
        self.clients = FakeClientsFacade()
        self.identity = FakeIdentityFacade()
        ctx = context()
        self.application_id: UUID = ctx.application_id
        self.organization_id: UUID = ctx.organization_id
        self.applications.add_card(
            builders.application_card(id=ctx.application_id, organization_id=ctx.organization_id)
        )
        self.head = self.identity.add_account(
            last_name="Смирнова", first_name="Анна", account_id=uuid4()
        )
        self.facts = ApplicationFacts(self.applications, self.clients, self.identity)

    def head_is_registry_head(self) -> None:
        self.clients.registry_heads[self.organization_id] = self.head.id


@pytest.fixture
def world() -> World:
    return World()


async def test_head_with_a_consent(world: World) -> None:
    world.head_is_registry_head()
    world.identity.give_consent(
        world.head.id, "credit_bureau_personal", NOW, NOW + timedelta(days=182)
    )

    fact = await world.facts.enrichment_request(world.application_id)

    assert fact.head == PersonFact(world.head.id, "Смирнова", "Анна", None)
    assert fact.head_bki_consent_at == NOW


async def test_head_without_a_consent(world: World) -> None:
    world.head_is_registry_head()
    world.identity.give_consent(world.head.id, "personal_data", NOW)

    fact = await world.facts.enrichment_request(world.application_id)

    assert fact.head is not None and fact.head.account_id == world.head.id
    assert fact.head_bki_consent_at is None


async def test_no_registry_head(world: World) -> None:
    world.identity.give_consent(world.head.id, "credit_bureau_personal", NOW)

    fact = await world.facts.enrichment_request(world.application_id)

    assert fact.head is None and fact.head_bki_consent_at is None


async def test_registry_head_without_an_account(world: World) -> None:
    world.clients.registry_heads[world.organization_id] = uuid4()

    fact = await world.facts.enrichment_request(world.application_id)

    assert fact.head is None and fact.head_bki_consent_at is None


async def _command(world: World) -> FetchEnrichment:
    node = Node("fetch", NodeType.TASK, "fetch", "fetch_enrichment", NodeConfig())
    result = await STEPS["fetch_enrichment"].run(StepInput(context(), node, NOW, world.facts))
    [request] = result.commands
    command = command_contract(request)
    assert isinstance(command, FetchEnrichment)
    return command


async def test_command_carries_the_head_and_the_consent(world: World) -> None:
    world.head_is_registry_head()
    world.identity.give_consent(world.head.id, "credit_bureau_personal", NOW)

    command = await _command(world)

    assert command.head == PersonRef(
        account_id=world.head.id, last_name="Смирнова", first_name="Анна", middle_name=None
    )
    assert command.head_bki_consent_at == NOW


async def test_command_without_a_consent_has_no_moment(world: World) -> None:
    world.head_is_registry_head()

    command = await _command(world)

    assert command.head is not None
    assert command.head_bki_consent_at is None


async def test_command_asks_every_source(world: World) -> None:
    command = await _command(world)

    assert command.sources == [
        "egrul",
        "fns",
        "bki",
        "statement",
        "gir_bo",
        "kontur",
        "bki_head",
        "aml",
        "bank_stop_list",
    ]


async def test_the_applicant_is_a_representative(world: World) -> None:
    """115-FZ: who acts for the client is screened too, on this very application."""
    world.head_is_registry_head()
    applicant = world.identity.add_account(
        last_name="Бухгалтерова", first_name="Вера", account_id=uuid4()
    )
    card = builders.application_card(
        id=world.application_id,
        organization_id=world.organization_id,
        applicant_account_id=applicant.id,
    )
    world.applications.add_card(card)

    command = await _command(world)

    assert command.representative == PersonRef(
        account_id=applicant.id, last_name="Бухгалтерова", first_name="Вера", middle_name=None
    )


async def test_the_head_applying_is_not_a_representative(world: World) -> None:
    world.head_is_registry_head()
    card = builders.application_card(
        id=world.application_id,
        organization_id=world.organization_id,
        applicant_account_id=world.head.id,
    )
    world.applications.add_card(card)

    command = await _command(world)

    assert command.head is not None and command.representative is None
