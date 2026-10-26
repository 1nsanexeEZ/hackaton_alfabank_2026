"""Reads behind the facade (ReadModelQueries): filters, sorts and pages."""

from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.projector.application.interfaces.repositories import ReadModelQueries
from src.modules.projector.domain.enums import QueueSort, ReviewKind
from src.modules.projector.domain.metrics import DailyMetrics
from src.modules.projector.domain.read_models import (
    ApplicationOverview,
    OrganizationDashboard,
    QueueItem,
)
from src.modules.projector.domain.timeline import CLIENT, TimelineEntry
from src.modules.projector.infrastructure.database.models import (
    ApplicationOverviewRow,
    BackofficeMetricsRow,
    OrganizationDashboardRow,
    TimelineEntryRow,
    UnderwritingQueueRow,
)
from src.modules.projector.infrastructure.repositories.mappers import to_record

Q = UnderwritingQueueRow

# due_at — the nearest deadline first; amount — the largest first; score — the
# riskiest first; created_at — the oldest first. Empty values go last.
_QUEUE_ORDER: dict[str, tuple[Any, ...]] = {
    "due_at": (Q.due_at.asc().nulls_last(),),
    "amount": (Q.amount.desc().nulls_last(),),
    "score": (Q.score.asc().nulls_last(),),
    "created_at": (),
}


class SqlAlchemyReadModelQueries(ReadModelQueries):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def overviews_of(
        self, organization_id: UUID, status: str | None, limit: int, offset: int
    ) -> tuple[list[ApplicationOverview], int]:
        conditions = [ApplicationOverviewRow.organization_id == organization_id]
        if status is not None:
            conditions.append(ApplicationOverviewRow.status == status)
        total = await self._session.scalar(
            select(func.count()).select_from(ApplicationOverviewRow).where(*conditions)
        )
        stmt = (
            select(ApplicationOverviewRow)
            .where(*conditions)
            .order_by(
                ApplicationOverviewRow.updated_at.desc(), ApplicationOverviewRow.application_id
            )
            .limit(limit)
            .offset(offset)
        )
        rows = (await self._session.scalars(stmt)).all()
        return [to_record(ApplicationOverview, row) for row in rows], total or 0

    async def application_groups(self) -> list[tuple[str, str, str, int, Decimal]]:
        row = ApplicationOverviewRow
        stmt = (
            select(
                row.status,
                row.product_code,
                func.max(row.product_name),
                func.count(),
                func.coalesce(func.sum(row.amount), 0),
            )
            .group_by(row.status, row.product_code)
            .order_by(row.status, row.product_code)
        )
        return [
            (status, code, name, int(count), Decimal(str(amount)))
            for status, code, name, count, amount in (await self._session.execute(stmt)).all()
        ]

    async def amount_buckets(self, edges: Sequence[Decimal]) -> list[int]:
        amount = ApplicationOverviewRow.amount
        bucket = case(
            *((amount < edge, index) for index, edge in enumerate(edges)), else_=len(edges)
        ).label("bucket")
        stmt = select(bucket, func.count()).where(amount.is_not(None), amount > 0).group_by(bucket)
        counts: dict[int, int] = dict((await self._session.execute(stmt)).tuples().all())
        return [int(counts.get(index, 0)) for index in range(len(edges) + 1)]

    async def latest_overviews(self, limit: int) -> list[ApplicationOverview]:
        stmt = (
            select(ApplicationOverviewRow)
            .order_by(
                ApplicationOverviewRow.updated_at.desc(), ApplicationOverviewRow.application_id
            )
            .limit(limit)
        )
        rows = (await self._session.scalars(stmt)).all()
        return [to_record(ApplicationOverview, row) for row in rows]

    async def get_dashboard(self, organization_id: UUID) -> OrganizationDashboard | None:
        row = await self._session.get(OrganizationDashboardRow, organization_id)
        return None if row is None else to_record(OrganizationDashboard, row)

    async def queue_of(
        self,
        role: str,
        statuses: tuple[str, ...],
        sort: QueueSort,
        limit: int,
        offset: int,
        review: ReviewKind | None = None,
    ) -> tuple[list[QueueItem], int]:
        # One row per application — its latest task: a returned application has
        # several, and it belongs to the tab of the one it is on now.
        ranked = (
            select(
                Q.task_id,
                func.row_number()
                .over(
                    partition_by=Q.application_id,
                    order_by=(Q.created_at.desc(), Q.task_id.desc()),
                )
                .label("rank"),
            )
            .where(Q.candidate_role == role)
            .subquery()
        )
        latest = select(ranked.c.task_id).where(ranked.c.rank == 1)
        conditions = [Q.candidate_role == role, Q.status.in_(statuses), Q.task_id.in_(latest)]
        if review is not None:
            conditions.append(Q.review == review)
        total = await self._session.scalar(select(func.count()).select_from(Q).where(*conditions))
        stmt = (
            select(Q)
            .where(*conditions)
            .order_by(*_QUEUE_ORDER.get(sort, _QUEUE_ORDER["due_at"]), Q.created_at, Q.task_id)
            .limit(limit)
            .offset(offset)
        )
        rows = (await self._session.scalars(stmt)).all()
        return [to_record(QueueItem, row) for row in rows], total or 0

    async def timeline_of(self, application_id: UUID, client_only: bool) -> list[TimelineEntry]:
        stmt = select(TimelineEntryRow).where(TimelineEntryRow.application_id == application_id)
        if client_only:
            stmt = stmt.where(TimelineEntryRow.audience == CLIENT)
        stmt = stmt.order_by(TimelineEntryRow.at, TimelineEntryRow.id)
        return [to_record(TimelineEntry, row) for row in (await self._session.scalars(stmt)).all()]

    async def metrics_between(self, date_from: date, date_to: date) -> list[DailyMetrics]:
        stmt = (
            select(BackofficeMetricsRow)
            .where(BackofficeMetricsRow.day >= date_from, BackofficeMetricsRow.day <= date_to)
            .order_by(BackofficeMetricsRow.day, BackofficeMetricsRow.product_code)
        )
        return [to_record(DailyMetrics, row) for row in (await self._session.scalars(stmt)).all()]
