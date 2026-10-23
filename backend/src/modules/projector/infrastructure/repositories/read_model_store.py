"""Writes of the projection (ReadModelStore)."""

from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, and_, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.projector.application.interfaces.repositories import ReadModelStore
from src.modules.projector.domain.metrics import DailyMetrics
from src.modules.projector.domain.read_models import (
    ApplicationOverview,
    OrganizationDashboard,
    QueueItem,
)
from src.modules.projector.domain.timeline import TimelineEntry
from src.modules.projector.infrastructure.database.models import (
    ApplicationOverviewRow,
    BackofficeMetricsRow,
    OrganizationDashboardRow,
    TimelineEntryRow,
    UnderwritingQueueRow,
)
from src.modules.projector.infrastructure.repositories.mappers import copy_to_row, to_record

ALL_ROWS: tuple[type[Any], ...] = (
    ApplicationOverviewRow,
    UnderwritingQueueRow,
    TimelineEntryRow,
    OrganizationDashboardRow,
    BackofficeMetricsRow,
)


def day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=UTC)
    return start, start + timedelta(days=1)


class SqlAlchemyReadModelStore(ReadModelStore):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _upsert(self, model: type[Any], key: Any, record: Any) -> None:
        row = await self._session.get(model, key)
        if row is None:
            row = model()
            self._session.add(row)
        copy_to_row(record, row)
        # Later reads of the same handler (counts, metrics) must see the change.
        await self._session.flush()

    # --- overview ---------------------------------------------------------------

    async def get_overview(self, application_id: UUID) -> ApplicationOverview | None:
        row = await self._session.get(ApplicationOverviewRow, application_id)
        return None if row is None else to_record(ApplicationOverview, row)

    async def save_overview(self, overview: ApplicationOverview) -> None:
        await self._upsert(ApplicationOverviewRow, overview.application_id, overview)

    async def overviews_for_metrics(
        self, day: date, product_code: str
    ) -> list[ApplicationOverview]:
        start, end = day_bounds(day)

        def within(column: Any) -> ColumnElement[bool]:
            return and_(column >= start, column < end)

        stmt = select(ApplicationOverviewRow).where(
            ApplicationOverviewRow.product_code == product_code,
            or_(
                within(ApplicationOverviewRow.submitted_at),
                within(ApplicationOverviewRow.decided_at),
                within(ApplicationOverviewRow.manual_review_at),
            ),
        )
        rows = (await self._session.scalars(stmt)).all()
        return [to_record(ApplicationOverview, row) for row in rows]

    async def count_applications(
        self, organization_id: UUID, active_statuses: frozenset[str]
    ) -> tuple[int, int]:
        of_organization = ApplicationOverviewRow.organization_id == organization_id
        active = await self._session.scalar(
            select(func.count())
            .select_from(ApplicationOverviewRow)
            .where(of_organization, ApplicationOverviewRow.status.in_(sorted(active_statuses)))
        )
        waiting = await self._session.scalar(
            select(func.count())
            .select_from(ApplicationOverviewRow)
            .where(of_organization, ApplicationOverviewRow.action_required != "none")
        )
        return active or 0, waiting or 0

    # --- queue ------------------------------------------------------------------

    async def get_queue_item(self, task_id: UUID) -> QueueItem | None:
        row = await self._session.get(UnderwritingQueueRow, task_id)
        return None if row is None else to_record(QueueItem, row)

    async def queue_items_of(self, application_id: UUID) -> list[QueueItem]:
        stmt = (
            select(UnderwritingQueueRow)
            .where(UnderwritingQueueRow.application_id == application_id)
            .order_by(UnderwritingQueueRow.created_at, UnderwritingQueueRow.task_id)
        )
        return [to_record(QueueItem, row) for row in (await self._session.scalars(stmt)).all()]

    async def save_queue_item(self, item: QueueItem) -> None:
        await self._upsert(UnderwritingQueueRow, item.task_id, item)

    # --- timeline ---------------------------------------------------------------

    async def add_timeline_entry(self, entry: TimelineEntry) -> bool:
        exists = await self._session.scalar(
            select(TimelineEntryRow.id).where(
                TimelineEntryRow.source_event_id == entry.source_event_id
            )
        )
        if exists is not None:
            return False
        row = TimelineEntryRow()
        copy_to_row(entry, row)
        self._session.add(row)
        await self._session.flush()
        return True

    # --- dashboard --------------------------------------------------------------

    async def get_dashboard(self, organization_id: UUID) -> OrganizationDashboard | None:
        row = await self._session.get(OrganizationDashboardRow, organization_id)
        return None if row is None else to_record(OrganizationDashboard, row)

    async def save_dashboard(self, dashboard: OrganizationDashboard) -> None:
        await self._upsert(OrganizationDashboardRow, dashboard.organization_id, dashboard)

    # --- metrics ----------------------------------------------------------------

    async def save_metrics(self, metrics: DailyMetrics) -> None:
        key = (metrics.day, metrics.product_code)
        if metrics.is_empty:
            row = await self._session.get(BackofficeMetricsRow, key)
            if row is not None:
                await self._session.delete(row)
                await self._session.flush()
            return
        await self._upsert(BackofficeMetricsRow, key, metrics)

    # --- rebuild ----------------------------------------------------------------

    async def clear(self) -> None:
        for model in ALL_ROWS:
            await self._session.execute(delete(model))
