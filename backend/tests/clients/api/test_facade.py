"""The real ClientsFacade on the seeded demo companies."""

import inspect
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from seed.demo_data import COMPANIES
from src.core.access.organizations import MemberOrganizationsResolver
from src.core.domain import Money
from src.core.exceptions.exceptions import NotFoundError, PermissionDeniedError
from src.modules.clients.domain.financial_report import FinancialReport, ReportFigures, ReportSource
from src.modules.clients.domain.value_objects import FiscalPeriod
from src.modules.clients.facade import ClientsFacade, DiscrepancyDTO, OrgPermission
from src.modules.clients.infrastructure.facade_impl import ClientsFacadeImpl, latest_annual
from src.modules.clients.infrastructure.repositories import SqlAlchemyFinancialReportRepository
from tests.clients.api.conftest import IVANOV, KUZNETSOVA, NOW, PETROV, SMIRNOVA, Demo
from tests.fakes import builders


@pytest.mark.parametrize("protocol", [ClientsFacade, MemberOrganizationsResolver])
def test_implementation_keeps_the_contract(protocol: type) -> None:
    for name, method in vars(protocol).items():
        if name.startswith("_") or not callable(method):
            continue
        implementation = getattr(ClientsFacadeImpl, name)
        assert inspect.iscoroutinefunction(implementation), name
        assert list(inspect.signature(implementation).parameters) == list(
            inspect.signature(method).parameters
        ), name


def test_facade_is_registered_under_both_keys(demo: Demo) -> None:
    registry = demo.app.state.facades
    assert isinstance(registry.get(ClientsFacade, None), ClientsFacadeImpl)
    assert isinstance(registry.get(MemberOrganizationsResolver, None), ClientsFacadeImpl)


def test_accountant_submits_but_does_not_sign(demo: Demo) -> None:
    """S-8: the accountant prepares and submits, only the director signs."""
    org_id, accountant = demo.orgs["romashka"], demo.id_of(KUZNETSOVA)

    async def check(facade: ClientsFacadeImpl) -> None:
        await facade.ensure_can(accountant, org_id, OrgPermission.SUBMIT_APPLICATION)
        await facade.ensure_can(accountant, org_id, "edit_financials")
        await facade.ensure_can(demo.id_of(SMIRNOVA), org_id, OrgPermission.SIGN)
        with pytest.raises(PermissionDeniedError):
            await facade.ensure_can(accountant, org_id, OrgPermission.SIGN)
        with pytest.raises(PermissionDeniedError):
            await facade.ensure_can(demo.id_of(PETROV), demo.orgs["vector"], OrgPermission.SIGN)
        with pytest.raises(NotFoundError):
            await facade.ensure_can(demo.id_of(PETROV), org_id, OrgPermission.VIEW)
        with pytest.raises(NotFoundError):
            await facade.ensure_can(accountant, uuid4(), OrgPermission.VIEW)
        with pytest.raises(ValueError):
            await facade.ensure_can(accountant, org_id, "fly")

    demo.facade_call(check)


def test_permissions_and_members(demo: Demo) -> None:
    org_id = demo.orgs["romashka"]
    smirnova, kuznetsova = demo.id_of(SMIRNOVA), demo.id_of(KUZNETSOVA)

    async def check(facade: ClientsFacadeImpl) -> None:
        assert await facade.get_member_permissions(kuznetsova, org_id) == frozenset(
            {"view", "submit_application", "edit_financials"}
        )
        assert await facade.get_member_permissions(uuid4(), org_id) == frozenset()
        assert await facade.get_member_permissions(kuznetsova, uuid4()) == frozenset()
        assert await facade.list_members(org_id, OrgPermission.SIGN) == [smirnova]
        assert set(await facade.list_members(org_id)) == {smirnova, kuznetsova}
        assert await facade.list_members(uuid4()) == []
        assert await facade.get_member_organization_ids(kuznetsova) == frozenset(
            {org_id, demo.orgs["ivanov"]}
        )
        assert await facade.member_organization_ids(demo.id_of(IVANOV)) == frozenset(
            {demo.orgs["ivanov"]}
        )

    demo.facade_call(check)


def test_registry_head_is_the_member_matched_by_name(demo: Demo) -> None:
    """Smirnova matched the registry as the director of Romashka; Petrov's name differs
    from the registry head of Vector, so Vector has no head to ask for a consent."""

    async def heads(facade: ClientsFacadeImpl):  # type: ignore[no-untyped-def]
        return (
            await facade.get_registry_head(demo.orgs["romashka"]),
            await facade.get_registry_head(demo.orgs["ivanov"]),
            await facade.get_registry_head(demo.orgs["vector"]),
            await facade.get_registry_head(uuid4()),
        )

    romashka, ivanov, vector, unknown = demo.facade_call(heads)
    assert romashka == demo.id_of(SMIRNOVA)
    assert ivanov == demo.id_of(IVANOV)
    assert vector is None and unknown is None


def test_my_organizations(demo: Demo) -> None:
    async def load(facade: ClientsFacadeImpl):  # type: ignore[no-untyped-def]
        return await facade.list_my_organizations(demo.id_of(KUZNETSOVA))

    summaries = demo.facade_call(load)
    assert [(s.inn, s.legal_form, s.my_role) for s in summaries] == [
        ("770669871605", "IE", "accountant"),
        ("7701158817", "LLC", "accountant"),
    ]
    assert summaries[0].my_permissions == frozenset(
        {"view", "submit_application", "edit_financials"}
    )


@pytest.mark.parametrize("company", COMPANIES, ids=[c.code for c in COMPANIES])
def test_snapshot_matches_the_builders(demo: Demo, company) -> None:  # type: ignore[no-untyped-def]
    org_id = demo.orgs[company.code]

    async def load(facade: ClientsFacadeImpl):  # type: ignore[no-untyped-def]
        return await facade.get_snapshot(org_id)

    snapshot = demo.facade_call(load)
    expected = builders.organization_snapshot(company.code, organization_id=org_id)
    assert snapshot.business_age_months == company.registered_months_ago
    # Seeds pick the employees count and the exact calendar date of registration.
    ignored = {
        "employees_count": snapshot.employees_count,
        "registered_at": snapshot.registered_at,
        "discrepancies": snapshot.discrepancies,
        "snapshot_at": snapshot.snapshot_at,
    }
    assert snapshot == replace(expected, **ignored)
    assert snapshot.snapshot_at == NOW


def test_vector_snapshot_shows_the_mismatch(demo: Demo) -> None:
    async def load(facade: ClientsFacadeImpl):  # type: ignore[no-untyped-def]
        return await facade.get_snapshot(demo.orgs["vector"])

    snapshot = demo.facade_call(load)
    assert snapshot.verification_status == "mismatch"
    assert snapshot.discrepancies == (
        DiscrepancyDTO(field="head_name", declared="Петров П. П.", registry="Сидоров С. С."),
    )
    assert snapshot.head_name == "Сидоров Сергей Сергеевич"


def test_unknown_snapshot(demo: Demo) -> None:
    async def load(facade: ClientsFacadeImpl) -> None:
        await facade.get_snapshot(uuid4())

    with pytest.raises(NotFoundError):
        demo.facade_call(load)


def test_snapshot_takes_two_latest_annual_reports(demo: Demo) -> None:
    org_id = demo.orgs["romashka"]

    async def add_reports() -> None:
        async with demo.app.state.session_factory() as session:
            reports = SqlAlchemyFinancialReportRepository(session)
            for period, source, revenue in (
                (FiscalPeriod(2023), ReportSource.DECLARED, 1),
                (FiscalPeriod(2026, 2), ReportSource.DECLARED, 2),
                (FiscalPeriod(2025), ReportSource.FNS, 3),
                (FiscalPeriod(2024), ReportSource.BANK_STATEMENT, 4),
            ):
                await reports.add(
                    FinancialReport(
                        id=uuid4(),
                        organization_id=org_id,
                        period=period,
                        source=source,
                        figures=ReportFigures(revenue=Money.of(revenue)),
                        submitted_at=NOW,
                    )
                )
            await session.commit()

    demo.run(add_reports)

    async def load(facade: ClientsFacadeImpl):  # type: ignore[no-untyped-def]
        return await facade.get_snapshot(org_id)

    reports = demo.facade_call(load).financial_reports
    # Quarters are skipped; per year the declared report wins over other sources.
    assert [(r.period_year, r.source, r.revenue) for r in reports] == [
        (2025, "declared", Decimal("48000000")),
        (2024, "declared", Decimal("40000000")),
    ]


def test_latest_annual_falls_back_to_other_sources() -> None:
    org_id = uuid4()
    moment = datetime(2026, 10, 21, tzinfo=UTC)

    def report(year: int, source: ReportSource) -> FinancialReport:
        return FinancialReport(
            id=uuid4(),
            organization_id=org_id,
            period=FiscalPeriod(year),
            source=source,
            figures=ReportFigures(revenue=Money.of(year)),
            submitted_at=moment,
        )

    chosen = latest_annual(
        [
            report(2023, ReportSource.DECLARED),
            report(2025, ReportSource.BANK_STATEMENT),
            report(2025, ReportSource.FNS),
            report(2024, ReportSource.DECLARED),
        ]
    )
    assert [(r.period.year, r.source) for r in chosen] == [
        (2025, ReportSource.FNS),
        (2024, ReportSource.DECLARED),
    ]
