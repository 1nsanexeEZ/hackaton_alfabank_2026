"""`ProjectorFacade` for bff: only calls the use cases, no logic of its own.
No access checks: bff checks the caller's rights before asking."""

from datetime import date
from uuid import UUID

from src.modules.projector.application.dto.applications import (
    ApplicationPageDTO,
    ApplicationStatsDTO,
    OrganizationDashboardDTO,
)
from src.modules.projector.application.dto.metrics import BackofficeMetricsDTO
from src.modules.projector.application.dto.queue import QueuePageDTO
from src.modules.projector.application.dto.timeline import TimelineEntryDTO
from src.modules.projector.application.use_cases.applications import (
    GetApplicationStatsUseCase,
    GetOrganizationDashboardUseCase,
    ListApplicationsUseCase,
)
from src.modules.projector.application.use_cases.metrics import GetBackofficeMetricsUseCase
from src.modules.projector.application.use_cases.queue import GetUnderwritingQueueUseCase
from src.modules.projector.application.use_cases.timeline import GetTimelineUseCase
from src.modules.projector.domain.enums import Audience, QueueSort, ReviewKind
from src.modules.projector.facade import ProjectorFacade


class ProjectorFacadeImpl(ProjectorFacade):
    def __init__(
        self,
        list_applications: ListApplicationsUseCase,
        get_organization_dashboard: GetOrganizationDashboardUseCase,
        get_underwriting_queue: GetUnderwritingQueueUseCase,
        get_timeline: GetTimelineUseCase,
        get_backoffice_metrics: GetBackofficeMetricsUseCase,
        get_application_stats: GetApplicationStatsUseCase,
    ) -> None:
        self._list_applications = list_applications
        self._get_organization_dashboard = get_organization_dashboard
        self._get_underwriting_queue = get_underwriting_queue
        self._get_timeline = get_timeline
        self._get_backoffice_metrics = get_backoffice_metrics
        self._get_application_stats = get_application_stats

    async def list_applications(
        self,
        organization_id: UUID,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> ApplicationPageDTO:
        return await self._list_applications.execute(organization_id, status, limit, offset)

    async def get_organization_dashboard(
        self, organization_id: UUID
    ) -> OrganizationDashboardDTO | None:
        return await self._get_organization_dashboard.execute(organization_id)

    async def get_application_stats(self, latest: int = 10) -> ApplicationStatsDTO:
        return await self._get_application_stats.execute(latest)

    async def get_underwriting_queue(
        self,
        role: str,
        status: str = "open",
        sort: QueueSort = "due_at",
        limit: int = 20,
        offset: int = 0,
        review: ReviewKind | None = None,
    ) -> QueuePageDTO:
        return await self._get_underwriting_queue.execute(role, status, sort, limit, offset, review)

    async def get_timeline(
        self, application_id: UUID, audience: Audience
    ) -> list[TimelineEntryDTO]:
        """audience=client returns client entries only; bank gets everything."""
        return await self._get_timeline.execute(application_id, audience)

    async def get_backoffice_metrics(self, date_from: date, date_to: date) -> BackofficeMetricsDTO:
        return await self._get_backoffice_metrics.execute(date_from, date_to)
