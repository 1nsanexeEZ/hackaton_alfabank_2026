from dataclasses import replace
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from src.core.domain import Money
from src.core.exceptions.exceptions import NotFoundError
from src.modules.clients.facade import FinancialReportDTO
from src.modules.enrichment.facade import CashflowForecastDTO
from src.modules.products.application.borrowers import BorrowerProfiles, borrower_profile
from tests.fakes import builders
from tests.fakes.clients_facade import FakeClientsFacade
from tests.fakes.enrichment_facade import FakeEnrichmentFacade


def test_profile_from_the_clients_snapshot() -> None:
    profile = borrower_profile(builders.organization_snapshot("ivanov"))
    assert profile.legal_form == "IE" and profile.business_age_months == 8
    assert profile.annual_revenue == Money.of(6_000_000)
    assert profile.okved_main == "62.01" and profile.okved_class == "62"
    assert profile.verified and profile.registry_status == "active"
    assert profile.in_msp_registry is None and profile.cash_gap_expected is None


def test_latest_annual_report_is_the_revenue() -> None:
    snapshot = builders.organization_snapshot("romashka")
    assert borrower_profile(snapshot).annual_revenue == Money.of(48_000_000)
    quarter = FinancialReportDTO(2026, 2, "declared", Decimal("99000000"))
    reordered = replace(
        snapshot, financial_reports=(quarter, *reversed(snapshot.financial_reports))
    )
    assert borrower_profile(reordered).annual_revenue == Money.of(48_000_000)
    assert borrower_profile(replace(snapshot, financial_reports=())).annual_revenue is None


def test_verification_and_registry_status() -> None:
    assert not borrower_profile(builders.organization_snapshot("vector")).verified
    assert borrower_profile(builders.organization_snapshot("zakat")).registry_status == (
        "liquidating"
    )


def _forecast(gap: bool) -> CashflowForecastDTO:
    return CashflowForecastDTO(
        months_history=(),
        forecast=(),
        gap_detected=gap,
        gap_month="2026-11" if gap else None,
        gap_amount=Decimal("150000") if gap else None,
        annual_inflow=Decimal("6000000"),
        revenue_confirmed=True,
        method="тест",
        statement_document_ids=(),
    )


@pytest.mark.parametrize("gap", [True, False])
async def test_cash_gap_comes_from_the_statement_forecast(gap: bool) -> None:
    clients = FakeClientsFacade()
    org = clients.add_organization(builders.organization_snapshot("ivanov"))
    enrichment = FakeEnrichmentFacade()
    enrichment.cashflows[org.id] = _forecast(gap)

    profile = await BorrowerProfiles(clients, enrichment).get(org.id)

    assert profile.cash_gap_expected is gap


async def test_no_statement_means_the_gap_is_unknown() -> None:
    """Без выписки разрыв неизвестен — None, а не «разрыва нет»."""
    clients = FakeClientsFacade()
    org = clients.add_organization(builders.organization_snapshot("romashka"))
    assert (
        await BorrowerProfiles(clients, FakeEnrichmentFacade()).get(org.id)
    ).cash_gap_expected is None
    assert (await BorrowerProfiles(clients).get(org.id)).cash_gap_expected is None


async def test_forecast_failure_leaves_the_gap_unknown() -> None:
    class BrokenEnrichment(FakeEnrichmentFacade):
        async def latest_cashflow(self, organization_id: UUID) -> CashflowForecastDTO | None:
            raise RuntimeError("database is down")

    clients = FakeClientsFacade()
    org = clients.add_organization(builders.organization_snapshot("romashka"))
    assert (
        await BorrowerProfiles(clients, BrokenEnrichment()).get(org.id)
    ).cash_gap_expected is None


async def test_unknown_company() -> None:
    with pytest.raises(NotFoundError):
        await BorrowerProfiles(FakeClientsFacade()).get(uuid4())
