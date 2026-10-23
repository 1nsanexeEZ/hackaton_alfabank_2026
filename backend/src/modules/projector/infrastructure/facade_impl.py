"""ProjectorFacade over the read model tables. No access checks: bff checks
the caller's rights before asking."""

from datetime import date, datetime
from typing import Any, Literal, cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.domain.clock import Clock
from src.modules.decision.facade import review_kind
from src.modules.projector.domain.metrics import DailyMetrics, MetricsSummary
from src.modules.projector.domain.read_models import MANUAL_REVIEW, QueueItem, queue_statuses
from src.modules.projector.domain.timeline import CLIENT
from src.modules.projector.facade import (
    ActionRequired,
    ApplicationOverviewDTO,
    ApplicationPageDTO,
    Audience,
    BackofficeMetricsDTO,
    DailyMetricsDTO,
    OrganizationDashboardDTO,
    QueueItemDTO,
    QueuePageDTO,
    QueueSort,
    TimelineEntryDTO,
)
from src.modules.projector.infrastructure.models import (
    ApplicationOverviewRow,
    BackofficeMetricsRow,
    OrganizationDashboardRow,
    TimelineEntryRow,
    UnderwritingQueueRow,
)
from src.modules.projector.infrastructure.repositories import aware, to_record

Q = UnderwritingQueueRow
EntryKind = Literal["status", "stage", "task", "decision"]

# due_at — the nearest deadline first; amount — the largest first; score — the
# riskiest first; created_at — the oldest first. Empty values go last.
_QUEUE_ORDER: dict[str, tuple[Any, ...]] = {
    "due_at": (Q.due_at.asc().nulls_last(),),
    "amount": (Q.amount.desc().nulls_last(),),
    "score": (Q.score.asc().nulls_last(),),
    "created_at": (),
}


class ProjectorFacadeImpl:
    def __init__(self, session: AsyncSession, clock: Clock) -> None:
        self._session = session
        self._clock = clock

    async def list_applications(
        self,
        organization_id: UUID,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> ApplicationPageDTO:
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
        return ApplicationPageDTO(items=tuple(_overview(row) for row in rows), total=total or 0)

    async def get_organization_dashboard(
        self, organization_id: UUID
    ) -> OrganizationDashboardDTO | None:
        row = await self._session.get(OrganizationDashboardRow, organization_id)
        if row is None:
            return None
        return OrganizationDashboardDTO(
            organization_id=row.organization_id,
            active_applications=row.active_applications,
            action_required_count=row.action_required_count,
            pre_approved_max_amount=row.pre_approved_max_amount,
            pre_approved_rate_from=row.pre_approved_rate_from,
            last_activity_at=aware(row.last_activity_at),
        )

    async def get_underwriting_queue(
        self,
        role: str,
        status: str = "open",
        sort: QueueSort = "due_at",
        limit: int = 20,
        offset: int = 0,
    ) -> QueuePageDTO:
        conditions = [Q.candidate_role == role, Q.status.in_(queue_statuses(status))]
        total = await self._session.scalar(select(func.count()).select_from(Q).where(*conditions))
        stmt = (
            select(Q)
            .where(*conditions)
            .order_by(*_QUEUE_ORDER.get(sort, _QUEUE_ORDER["due_at"]), Q.created_at, Q.task_id)
            .limit(limit)
            .offset(offset)
        )
        now = self._clock.now()
        items = [to_record(QueueItem, row) for row in (await self._session.scalars(stmt)).all()]
        return QueuePageDTO(items=tuple(_queue_item(i, now) for i in items), total=total or 0)

    async def get_timeline(
        self, application_id: UUID, audience: Audience
    ) -> list[TimelineEntryDTO]:
        """audience=client returns client entries only; bank gets everything."""
        stmt = select(TimelineEntryRow).where(TimelineEntryRow.application_id == application_id)
        if audience == CLIENT:
            stmt = stmt.where(TimelineEntryRow.audience == CLIENT)
        stmt = stmt.order_by(TimelineEntryRow.at, TimelineEntryRow.id)
        return [
            TimelineEntryDTO(
                id=row.id,
                application_id=row.application_id,
                at=aware(row.at),
                kind=cast(EntryKind, row.kind),
                title=row.title,
                audience=cast(Audience, row.audience),
                details=dict(row.details or {}),
            )
            for row in (await self._session.scalars(stmt)).all()
        ]

    async def get_backoffice_metrics(self, date_from: date, date_to: date) -> BackofficeMetricsDTO:
        stmt = (
            select(BackofficeMetricsRow)
            .where(BackofficeMetricsRow.day >= date_from, BackofficeMetricsRow.day <= date_to)
            .order_by(BackofficeMetricsRow.day, BackofficeMetricsRow.product_code)
        )
        cells = [to_record(DailyMetrics, row) for row in (await self._session.scalars(stmt)).all()]
        summary = MetricsSummary.of(cells)
        return BackofficeMetricsDTO(
            date_from=date_from,
            date_to=date_to,
            rows=tuple(
                DailyMetricsDTO(
                    day=c.day,
                    product_code=c.product_code,
                    submitted=c.submitted,
                    approved=c.approved,
                    counter_offers=c.counter_offers,
                    rejected=c.rejected,
                    manual_reviews=c.manual_reviews,
                    auto_decisions=c.auto_decisions,
                    avg_time_to_decision_sec=c.avg_time_to_decision_sec,
                )
                for c in cells
            ),
            submitted=summary.submitted,
            decided=summary.decided,
            auto_decision_share=summary.auto_decision_share,
            avg_time_to_decision_sec=summary.avg_time_to_decision_sec,
        )


def _overview(row: ApplicationOverviewRow) -> ApplicationOverviewDTO:
    return ApplicationOverviewDTO(
        application_id=row.application_id,
        organization_id=row.organization_id,
        number=row.number,
        product_code=row.product_code,
        product_name=row.product_name,
        amount=row.amount,
        term_months=row.term_months,
        status=row.status,
        client_stage=row.client_stage,
        action_required=cast(ActionRequired, row.action_required),
        offer_amount=row.offer_amount,
        offer_rate=row.offer_rate,
        submitted_at=aware(row.submitted_at),
        updated_at=aware(row.updated_at),
    )


def _queue_item(item: QueueItem, now: datetime) -> QueueItemDTO:
    return QueueItemDTO(
        task_id=item.task_id,
        application_id=item.application_id,
        number=item.number,
        company_name=item.company_name,
        inn=item.inn,
        product_code=item.product_code,
        amount=item.amount,
        score=item.score,
        risk_grade=item.risk_grade,
        cash_gap=item.cash_gap,
        routing_reasons=item.routing_reasons,
        due_at=item.due_at,
        overdue=item.is_overdue(now),
        assignee_id=item.assignee_id,
        status=item.status,
        created_at=item.created_at,
        review=review_kind(MANUAL_REVIEW, item.routing_reasons) if item.routing_reasons else None,
    )
