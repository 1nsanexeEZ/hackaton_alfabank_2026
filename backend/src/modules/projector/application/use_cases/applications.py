"""Reads of the client's screens: the list of applications and the company dashboard."""

from decimal import Decimal
from typing import cast
from uuid import UUID

from src.modules.projector.application.dto.applications import (
    AmountBucketDTO,
    ApplicationGroupDTO,
    ApplicationOverviewDTO,
    ApplicationPageDTO,
    ApplicationStatsDTO,
    LatestApplicationDTO,
    OrganizationDashboardDTO,
)
from src.modules.projector.application.interfaces.repositories import ReadModelQueries
from src.modules.projector.domain.enums import ActionRequired
from src.modules.projector.domain.read_models import ApplicationOverview


class ListApplicationsUseCase:
    def __init__(self, read_models: ReadModelQueries) -> None:
        self._read_models = read_models

    async def execute(
        self,
        organization_id: UUID,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> ApplicationPageDTO:
        overviews, total = await self._read_models.overviews_of(
            organization_id, status, limit, offset
        )
        return ApplicationPageDTO(items=tuple(_overview(o) for o in overviews), total=total)


# Edges of the amount buckets, rubles: up to 1 mln, 1–3, 3–10, 10–30, 30+.
AMOUNT_EDGES = (Decimal(1_000_000), Decimal(3_000_000), Decimal(10_000_000), Decimal(30_000_000))


class GetApplicationStatsUseCase:
    """The bank's overview of the applications: groups by status and product, amount
    buckets and the latest rows — by the database, over all applications."""

    def __init__(self, read_models: ReadModelQueries) -> None:
        self._read_models = read_models

    async def execute(self, latest: int = 10) -> ApplicationStatsDTO:
        groups = await self._read_models.application_groups()
        buckets = await self._read_models.amount_buckets(AMOUNT_EDGES)
        rows = await self._read_models.latest_overviews(latest)
        bounds = (Decimal(0), *AMOUNT_EDGES)
        return ApplicationStatsDTO(
            groups=tuple(ApplicationGroupDTO(*group) for group in groups),
            amount_buckets=tuple(
                AmountBucketDTO(low, AMOUNT_EDGES[i] if i < len(AMOUNT_EDGES) else None, count)
                for i, (low, count) in enumerate(zip(bounds, buckets, strict=True))
            ),
            latest=tuple(_latest(row) for row in rows),
        )


class GetOrganizationDashboardUseCase:
    def __init__(self, read_models: ReadModelQueries) -> None:
        self._read_models = read_models

    async def execute(self, organization_id: UUID) -> OrganizationDashboardDTO | None:
        dashboard = await self._read_models.get_dashboard(organization_id)
        if dashboard is None:
            return None
        return OrganizationDashboardDTO(
            organization_id=dashboard.organization_id,
            active_applications=dashboard.active_applications,
            action_required_count=dashboard.action_required_count,
            pre_approved_max_amount=dashboard.pre_approved_max_amount,
            pre_approved_rate_from=dashboard.pre_approved_rate_from,
            last_activity_at=dashboard.last_activity_at,
        )


def _latest(overview: ApplicationOverview) -> LatestApplicationDTO:
    return LatestApplicationDTO(
        application_id=overview.application_id,
        organization_id=overview.organization_id,
        number=overview.number,
        company_name=overview.company_name,
        inn=overview.inn,
        product_code=overview.product_code,
        product_name=overview.product_name,
        amount=overview.amount,
        status=overview.status,
        client_stage=overview.client_stage,
        submitted_at=overview.submitted_at,
        updated_at=overview.updated_at,
    )


def _overview(overview: ApplicationOverview) -> ApplicationOverviewDTO:
    return ApplicationOverviewDTO(
        application_id=overview.application_id,
        organization_id=overview.organization_id,
        number=overview.number,
        product_code=overview.product_code,
        product_name=overview.product_name,
        amount=overview.amount,
        term_months=overview.term_months,
        status=overview.status,
        client_stage=overview.client_stage,
        action_required=cast(ActionRequired, overview.action_required),
        offer_amount=overview.offer_amount,
        offer_rate=overview.offer_rate,
        submitted_at=overview.submitted_at,
        updated_at=overview.updated_at,
    )
