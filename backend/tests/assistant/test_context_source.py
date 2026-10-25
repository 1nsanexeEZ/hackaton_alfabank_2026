"""The adapter over the real facades: access as on the client's card, the right to
sign from the company, and nothing of the bank's internals in the views."""

from dataclasses import replace
from decimal import Decimal
from uuid import uuid4

import pytest

from src.modules.assistant.domain.exceptions import ApplicationNotFoundError
from src.modules.assistant.domain.views import Viewer
from src.modules.assistant.infrastructure.adapters.context_source import FacadeContextSource
from tests.bff import factories
from tests.fakes import builders
from tests.fakes.applications_facade import FakeApplicationsFacade
from tests.fakes.clients_facade import FakeClientsFacade
from tests.fakes.decision_facade import FakeDecisionFacade
from tests.fakes.products_facade import FakeProductsFacade


class World:
    def __init__(self) -> None:
        self.applications = FakeApplicationsFacade()
        self.decision = FakeDecisionFacade()
        self.products = FakeProductsFacade()
        self.clients = FakeClientsFacade()
        self.romashka = self.clients.add_organization(builders.organization_snapshot("romashka"))
        self.vector = self.clients.add_organization(builders.organization_snapshot("vector"))
        self.director, self.accountant, self.stranger = uuid4(), uuid4(), uuid4()
        self.clients.add_member(self.director, self.romashka.id, "director")
        self.clients.add_member(self.accountant, self.romashka.id, "accountant")
        self.clients.add_member(self.stranger, self.vector.id, "director")
        self.products.add_product(builders.product("UNSECURED", name="Кредит без залога"))
        self.card = self.applications.add_card(
            builders.application_card(self.romashka, status="offer_ready")
        )
        self.decision.add_decision(factories.decision(self.card.id))

    def source(self) -> FacadeContextSource:
        return FacadeContextSource(self.applications, self.decision, self.products, self.clients)

    def client(self, account_id: object) -> Viewer:
        organizations = frozenset(
            org for (account, org) in self.clients.members if account == account_id
        )
        return Viewer(account_id=account_id, organization_ids=organizations)  # type: ignore[arg-type]


@pytest.fixture
def world() -> World:
    return World()


async def test_a_member_reads_the_card_and_the_right_to_sign(world: World) -> None:
    director = await world.source().get_application(world.client(world.director), world.card.id)
    accountant = await world.source().get_application(world.client(world.accountant), world.card.id)
    assert director.number == world.card.number and director.status == "offer_ready"
    assert director.request is not None and director.request.amount == Decimal("3000000")
    assert director.viewer_can_sign is True
    assert accountant.viewer_can_sign is False


async def test_a_stranger_and_a_missing_application_are_the_same_404(world: World) -> None:
    with pytest.raises(ApplicationNotFoundError):
        await world.source().get_application(world.client(world.stranger), world.card.id)
    with pytest.raises(ApplicationNotFoundError):
        await world.source().get_application(world.client(world.director), uuid4())
    with pytest.raises(ApplicationNotFoundError):
        await world.source().get_client_decision(world.client(world.stranger), world.card.id)


async def test_staff_read_any_card_but_have_no_list(world: World) -> None:
    staff = Viewer(account_id=uuid4(), organization_ids=None)
    view = await world.source().get_application(staff, world.card.id)
    assert view.viewer_can_sign is False
    assert await world.source().list_applications(staff) == []


async def test_the_list_holds_the_members_companies_only(world: World) -> None:
    world.applications.add_card(builders.application_card(world.vector))
    rows = await world.source().list_applications(world.client(world.director))
    assert [r.id for r in rows] == [world.card.id]


async def test_the_decision_is_the_clients_view(world: World) -> None:
    decision = await world.source().get_client_decision(world.client(world.director), world.card.id)
    assert decision is not None
    assert decision.outcome == "APPROVE"
    assert decision.terms is not None and decision.terms.rate == Decimal("19.5")
    # The view has no place for reason codes, a rule trace or limits.
    assert not {"reason_codes", "rule_trace", "limits"} & set(type(decision).__slots__)


async def test_the_company_name_and_inn_stay_behind(world: World) -> None:
    view = await world.source().get_application(world.client(world.director), world.card.id)
    text = repr(view)
    assert world.romashka.name not in text
    assert world.romashka.inn not in text


async def test_payments_come_from_the_products_formula(world: World) -> None:
    payment = world.source().calculate_payment(Decimal("2000000"), 24, Decimal("19.5"), "annuity")
    schedule = world.products.calculate_payment(Decimal("2000000"), 24, Decimal("19.5"), "annuity")
    assert payment.monthly_payment == schedule.monthly_payment
    with pytest.raises(ValueError):
        world.source().calculate_payment(Decimal("2000000"), 24, Decimal("19.5"), "weekly")


async def test_a_card_is_read_once_per_answer(world: World) -> None:
    source = world.source()
    viewer = world.client(world.director)
    first = await source.get_application(viewer, world.card.id)
    world.applications.add_card(replace(world.card, status="signing"))
    assert (await source.get_application(viewer, world.card.id)) is first
