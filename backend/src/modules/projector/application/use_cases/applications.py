"""Reads of the client's screens: the list of applications and the company dashboard."""

from typing import cast
from uuid import UUID

from src.modules.projector.application.dto.applications import (
    ApplicationOverviewDTO,
    ApplicationPageDTO,
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
