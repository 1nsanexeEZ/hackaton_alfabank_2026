"""Read of the underwriting queue."""

from datetime import datetime

from src.core.domain.clock import Clock
from src.modules.decision.facade import review_kind
from src.modules.projector.application.dto.queue import QueueItemDTO, QueuePageDTO
from src.modules.projector.application.interfaces.repositories import ReadModelQueries
from src.modules.projector.domain.enums import QueueSort
from src.modules.projector.domain.read_models import MANUAL_REVIEW, QueueItem, queue_statuses


class GetUnderwritingQueueUseCase:
    def __init__(self, read_models: ReadModelQueries, clock: Clock) -> None:
        self._read_models = read_models
        self._clock = clock

    async def execute(
        self,
        role: str,
        status: str = "open",
        sort: QueueSort = "due_at",
        limit: int = 20,
        offset: int = 0,
    ) -> QueuePageDTO:
        items, total = await self._read_models.queue_of(
            role, queue_statuses(status), sort, limit, offset
        )
        now = self._clock.now()
        return QueuePageDTO(items=tuple(_queue_item(i, now) for i in items), total=total)


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
