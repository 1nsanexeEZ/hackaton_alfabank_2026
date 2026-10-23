"""The borrower as products see it: built from the clients snapshot, with the
cash flow forecast from enrichment when the company has ever sent a bank
statement."""

import logging
from decimal import Decimal
from uuid import UUID

from src.core.domain import Money
from src.modules.clients.facade import ClientsFacade, OrganizationSnapshotDTO
from src.modules.enrichment.facade import EnrichmentFacade
from src.modules.products.domain.value_objects import BorrowerProfile

logger = logging.getLogger(__name__)


def annual_revenues(snapshot: OrganizationSnapshotDTO) -> list[Decimal]:
    """Revenues of annual reports, newest first (the snapshot keeps that order)."""
    reports = [r for r in snapshot.financial_reports if r.period_quarter is None]
    reports.sort(key=lambda r: r.period_year, reverse=True)
    return [r.revenue for r in reports]


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
    def __init__(self, clients: ClientsFacade, enrichment: EnrichmentFacade | None = None) -> None:
        self._clients = clients
        self._enrichment = enrichment

    async def get(self, organization_id: UUID) -> BorrowerProfile:
        """NotFoundError from clients when there is no such company."""
        snapshot = await self._clients.get_snapshot(organization_id)
        return borrower_profile(snapshot, await self._cash_gap(organization_id))

    async def _cash_gap(self, organization_id: UUID) -> bool | None:
        """The gap from the latest statement forecast; None — no statement yet, so the
        gap is unknown (not "no gap")."""
        if self._enrichment is None:
            return None
        try:
            forecast = await self._enrichment.latest_cashflow(organization_id)
        except Exception:
            # Matching must work without the forecast: the flag is just unknown.
            logger.warning("Cash flow forecast failed, cash gap is unknown", exc_info=True)
            return None
        return forecast.gap_detected if forecast is not None else None
