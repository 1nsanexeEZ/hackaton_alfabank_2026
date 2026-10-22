"""The borrower as products see it: built from the clients snapshot, with the
cash gap forecast from scoring when the scoring module is there."""

import logging
from collections.abc import Iterable
from decimal import Decimal
from uuid import UUID

from src.core.domain import Money
from src.modules.clients.facade import ClientsFacade, OrganizationSnapshotDTO
from src.modules.products.domain.value_objects import BorrowerProfile
from src.modules.scoring.facade import CompanyProfileDTO, ScoringFacade

logger = logging.getLogger(__name__)

# Scoring flags meaning a cash gap is expected (`cash_gap`, `cash_gap_<detail>`).
CASH_GAP_FLAG = "cash_gap"


def annual_revenues(snapshot: OrganizationSnapshotDTO) -> list[Decimal]:
    """Revenues of annual reports, newest first (the snapshot keeps that order)."""
    reports = [r for r in snapshot.financial_reports if r.period_quarter is None]
    reports.sort(key=lambda r: r.period_year, reverse=True)
    return [r.revenue for r in reports]


def has_cash_gap_flag(flags: Iterable[str]) -> bool:
    return any(f == CASH_GAP_FLAG or f.startswith(f"{CASH_GAP_FLAG}_") for f in flags)


def company_profile(snapshot: OrganizationSnapshotDTO) -> CompanyProfileDTO:
    revenues = annual_revenues(snapshot)
    return CompanyProfileDTO(
        legal_form=snapshot.legal_form,
        business_age_months=snapshot.business_age_months,
        okved_main=snapshot.okved_main,
        annual_revenue=revenues[0] if revenues else None,
        previous_annual_revenue=revenues[1] if len(revenues) > 1 else None,
        verification_status=snapshot.verification_status,
        registry_status=snapshot.registry_status,
    )


def borrower_profile(
    snapshot: OrganizationSnapshotDTO, cash_gap_expected: bool | None = None
) -> BorrowerProfile:
    revenues = annual_revenues(snapshot)
    return BorrowerProfile(
        legal_form=snapshot.legal_form,
        business_age_months=snapshot.business_age_months,
        annual_revenue=Money(revenues[0]) if revenues else None,
        okved_main=snapshot.okved_main,
        verified=snapshot.verification_status == "verified",
        registry_status=snapshot.registry_status,
        in_msp_registry=None,
        cash_gap_expected=cash_gap_expected,
    )


class BorrowerProfiles:
    def __init__(self, clients: ClientsFacade, scoring: ScoringFacade | None = None) -> None:
        self._clients = clients
        self._scoring = scoring

    async def get(self, organization_id: UUID, amount: Decimal | None = None) -> BorrowerProfile:
        """NotFoundError from clients when there is no such company."""
        snapshot = await self._clients.get_snapshot(organization_id)
        return borrower_profile(snapshot, self._cash_gap(snapshot, amount))

    def _cash_gap(self, snapshot: OrganizationSnapshotDTO, amount: Decimal | None) -> bool | None:
        if self._scoring is None:
            return None
        try:
            estimate = self._scoring.estimate(company_profile(snapshot), amount)
        except Exception:
            # Matching must work without the forecast: the flag is just unknown.
            logger.warning("Scoring estimate failed, cash gap is unknown", exc_info=True)
            return None
        return has_cash_gap_flag(estimate.flags)
