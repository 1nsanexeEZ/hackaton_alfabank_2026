"""Fakes must keep the shape of the facades they stand in for: same methods,
same parameters, async where the facade is async."""

import inspect
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest

from src.core.access.organizations import MemberOrganizationsResolver
from src.core.exceptions.exceptions import NotFoundError, PermissionDeniedError
from src.modules.applications.facade import ApplicationsFacade
from src.modules.clients.facade import ClientsFacade, OrgPermission
from src.modules.decision.facade import DecisionFacade
from src.modules.enrichment.facade import EnrichmentFacade
from src.modules.identity.facade import IdentityFacade
from src.modules.market.facade import MarketFacade
from src.modules.notifications.facade import NotificationsFacade
from src.modules.process.facade import ProcessFacade
from src.modules.products.facade import ProductsFacade
from src.modules.projector.facade import ProjectorFacade
from src.modules.scoring.facade import ScoringFacade
from tests.fakes import builders
from tests.fakes.applications_facade import FakeApplicationsFacade
from tests.fakes.clients_facade import FakeClientsFacade
from tests.fakes.decision_facade import FakeDecisionFacade
from tests.fakes.enrichment_facade import FakeEnrichmentFacade
from tests.fakes.identity_facade import FakeIdentityFacade
from tests.fakes.market_facade import FakeMarketFacade
from tests.fakes.notifications_facade import FakeNotificationsFacade
from tests.fakes.process_facade import FakeProcessFacade
from tests.fakes.products_facade import FakeProductsFacade
from tests.fakes.projector_facade import FakeProjectorFacade
from tests.fakes.scoring_facade import FakeScoringFacade

PAIRS: list[tuple[type[Any], type[Any]]] = [
    (IdentityFacade, FakeIdentityFacade),
    (ClientsFacade, FakeClientsFacade),
    (MemberOrganizationsResolver, FakeClientsFacade),
    (ProductsFacade, FakeProductsFacade),
    (ApplicationsFacade, FakeApplicationsFacade),
    (ProcessFacade, FakeProcessFacade),
    (EnrichmentFacade, FakeEnrichmentFacade),
    (ScoringFacade, FakeScoringFacade),
    (DecisionFacade, FakeDecisionFacade),
    (NotificationsFacade, FakeNotificationsFacade),
    (ProjectorFacade, FakeProjectorFacade),
    (MarketFacade, FakeMarketFacade),
]


def protocol_methods(protocol: type[Any]) -> dict[str, Any]:
    return {
        name: member
        for name, member in vars(protocol).items()
        if callable(member) and not name.startswith("_")
    }


@pytest.mark.parametrize("protocol,fake", PAIRS, ids=[p.__name__ for p, _ in PAIRS])
def test_fake_matches_protocol(protocol: type[Any], fake: type[Any]) -> None:
    methods = protocol_methods(protocol)
    assert methods, f"{protocol.__name__} declares no methods"
    for name, method in methods.items():
        implementation = getattr(fake, name, None)
        assert implementation is not None, f"{fake.__name__} lacks {name}"
        assert inspect.iscoroutinefunction(implementation) == inspect.iscoroutinefunction(method), (
            f"{fake.__name__}.{name}: async mismatch"
        )
        expected = list(inspect.signature(method).parameters)
        actual = list(inspect.signature(implementation).parameters)
        assert actual == expected, f"{fake.__name__}.{name}: {actual} != {expected}"


async def test_clients_fake_follows_the_rights_table() -> None:
    clients = FakeClientsFacade()
    org = clients.add_organization(builders.organization_snapshot("romashka"))
    director, accountant, stranger = uuid4(), uuid4(), uuid4()
    clients.add_member(director, org.id, "director")
    clients.add_member(accountant, org.id, "accountant")

    await clients.ensure_can(director, org.id, OrgPermission.SIGN)
    await clients.ensure_can(accountant, org.id, OrgPermission.SUBMIT_APPLICATION)
    with pytest.raises(PermissionDeniedError):
        await clients.ensure_can(accountant, org.id, OrgPermission.SIGN)
    with pytest.raises(NotFoundError):
        await clients.ensure_can(stranger, org.id, OrgPermission.VIEW)
    assert await clients.member_organization_ids(accountant) == frozenset({org.id})
    assert set(await clients.list_members(org.id, OrgPermission.SIGN)) == {director}


def test_products_fake_payment_formula() -> None:
    schedule = FakeProductsFacade().calculate_payment(
        Decimal("1200000"), 12, Decimal("0"), "annuity"
    )
    assert schedule.monthly_payment == Decimal("100000.00")
    assert sum(p.principal for p in schedule.payments) == Decimal("1200000")
    assert schedule.payments[-1].balance_after == 0

    annuity = FakeProductsFacade().calculate_payment(
        Decimal("3000000"), 24, Decimal("24"), "annuity"
    )
    # 3 000 000 at 24 % for 24 months: 158 613.29 per month
    assert annuity.monthly_payment == Decimal("158613.29")
    assert sum(p.principal for p in annuity.payments) == Decimal("3000000")


def test_builders_use_demo_data() -> None:
    snapshot = builders.organization_snapshot("ivanov")
    assert snapshot.inn == "770669871605" and snapshot.kpp is None
    assert snapshot.legal_form == "IE" and len(snapshot.financial_reports) == 1
    card = builders.application_card(snapshot)
    assert builders.scoring_input(card).organization.inn == "770669871605"
