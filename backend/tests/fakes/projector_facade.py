from datetime import date
from uuid import UUID

from src.projector.facade import (
    ApplicationOverviewDTO,
    ApplicationPageDTO,
    Audience,
    BackofficeMetricsDTO,
    OrganizationDashboardDTO,
    QueueItemDTO,
    QueuePageDTO,
    QueueSort,
    TimelineEntryDTO,
)


class FakeProjectorFacade:
    def __init__(self) -> None:
        self.overviews: dict[UUID, ApplicationOverviewDTO] = {}
        self.dashboards: dict[UUID, OrganizationDashboardDTO] = {}
        self.queue: dict[UUID, QueueItemDTO] = {}
        self.timeline: list[TimelineEntryDTO] = []
        self.metrics: BackofficeMetricsDTO | None = None

    def add_overview(self, row: ApplicationOverviewDTO) -> ApplicationOverviewDTO:
        self.overviews[row.application_id] = row
        return row

    def add_queue_item(self, row: QueueItemDTO) -> QueueItemDTO:
        self.queue[row.task_id] = row
        return row

    def add_timeline_entry(self, entry: TimelineEntryDTO) -> TimelineEntryDTO:
        self.timeline.append(entry)
        return entry

    async def list_applications(
        self,
        organization_id: UUID,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> ApplicationPageDTO:
        rows = sorted(
            (
                r
                for r in self.overviews.values()
                if r.organization_id == organization_id and (status is None or r.status == status)
            ),
            key=lambda r: r.updated_at,
            reverse=True,
        )
        return ApplicationPageDTO(items=tuple(rows[offset : offset + limit]), total=len(rows))

    async def get_organization_dashboard(
        self, organization_id: UUID
    ) -> OrganizationDashboardDTO | None:
        return self.dashboards.get(organization_id)

    async def get_underwriting_queue(
        self,
        role: str,
        status: str = "open",
        sort: QueueSort = "due_at",
        limit: int = 20,
        offset: int = 0,
    ) -> QueuePageDTO:
        rows = [r for r in self.queue.values() if r.status == status]
        return QueuePageDTO(items=tuple(rows[offset : offset + limit]), total=len(rows))

    async def get_timeline(
        self, application_id: UUID, audience: Audience
    ) -> list[TimelineEntryDTO]:
        return sorted(
            (
                e
                for e in self.timeline
                if e.application_id == application_id
                and (audience == "bank" or e.audience == "client")
            ),
            key=lambda e: e.at,
        )

    async def get_backoffice_metrics(self, date_from: date, date_to: date) -> BackofficeMetricsDTO:
        if self.metrics is not None:
            return self.metrics
        return BackofficeMetricsDTO(date_from, date_to, (), 0, 0, None, None)
