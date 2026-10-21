from dataclasses import replace
from decimal import Decimal
from uuid import uuid4

import pytest

from src.clients.facade import FinancialReportDTO
from src.core.domain import Money
from src.core.exceptions.exceptions import NotFoundError
from src.products.application.borrowers import (
    BorrowerProfiles,
    borrower_profile,
    company_profile,
    has_cash_gap_flag,
)
from src.scoring.facade import CompanyProfileDTO, EstimateDTO
from tests.fakes import builders
from tests.fakes.clients_facade import FakeClientsFacade
from tests.fakes.scoring_facade import FakeScoringFacade


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


def test_company_profile_for_scoring() -> None:
    profile = company_profile(builders.organization_snapshot("romashka"))
    assert profile == CompanyProfileDTO(
        legal_form="LLC",
        business_age_months=72,
        okved_main="56.10",
        annual_revenue=Decimal("48000000"),
        previous_annual_revenue=Decimal("40000000"),
        verification_status="verified",
        registry_status="active",
    )


@pytest.mark.parametrize(
    "flags,expected",
    [
        ((), False),
        (("cash_gap",), True),
        (("cash_gap_in_2_months",), True),
        (("low_revenue", "cash_gap"), True),
        (("no_cash_gap_data",), False),
    ],
)
def test_cash_gap_flag(flags: tuple[str, ...], expected: bool) -> None:
    assert has_cash_gap_flag(flags) is expected


async def test_cash_gap_comes_from_the_scoring_estimate() -> None:
    clients = FakeClientsFacade()
    org = clients.add_organization(builders.organization_snapshot("ivanov"))
    scoring = FakeScoringFacade(EstimateDTO(score=610, grade="C", flags=("cash_gap",), factors=()))

    profile = await BorrowerProfiles(clients, scoring).get(org.id, Decimal("1000000"))

    assert profile.cash_gap_expected is True
    assert scoring.estimate_calls[0].okved_main == "62.01"
    assert (
        await BorrowerProfiles(clients, FakeScoringFacade()).get(org.id)
    ).cash_gap_expected is False
    assert (await BorrowerProfiles(clients).get(org.id)).cash_gap_expected is None


async def test_scoring_failure_leaves_the_forecast_unknown() -> None:
    class BrokenScoring(FakeScoringFacade):
        def estimate(
            self, company: CompanyProfileDTO, amount: Decimal | None = None
        ) -> EstimateDTO:
            raise RuntimeError("model is not loaded")

    clients = FakeClientsFacade()
    org = clients.add_organization(builders.organization_snapshot("romashka"))
    assert (await BorrowerProfiles(clients, BrokenScoring()).get(org.id)).cash_gap_expected is None


async def test_unknown_company() -> None:
    with pytest.raises(NotFoundError):
        await BorrowerProfiles(FakeClientsFacade()).get(uuid4())
