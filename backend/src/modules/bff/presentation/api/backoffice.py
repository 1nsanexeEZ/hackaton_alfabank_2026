from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from src.core.access.dependencies import require_permissions
from src.core.access.permissions import Permissions
from src.modules.bff.presentation.dependencies import (
    BackofficeMetricsDep,
    CanReadBackoffice,
    UnderwriterCardDep,
    UnderwritingQueueDep,
)
from src.modules.bff.presentation.schemas.backoffice import UnderwriterCard
from src.modules.projector.facade import BackofficeMetricsDTO, QueuePageDTO, QueueSort

router = APIRouter(prefix="/bff/backoffice", tags=["bff"])


@router.get(
    "/queue",
    response_model=QueuePageDTO,
    dependencies=[Depends(require_permissions(Permissions.TASKS_READ))],
)
async def underwriting_queue(
    _: CanReadBackoffice,
    use_case: UnderwritingQueueDep,
    # open — waiting for a person (taken tasks too), closed — done or cancelled.
    status: Literal["open", "closed", "in_progress", "done", "cancelled"] = "open",
    sort: QueueSort = "due_at",
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> QueuePageDTO:
    return await use_case.execute(status, sort, limit, offset)


@router.get(
    "/applications/{application_id}",
    response_model=UnderwriterCard,
    dependencies=[Depends(require_permissions(Permissions.DECISIONS_READ))],
)
async def underwriter_card(
    application_id: UUID, _: CanReadBackoffice, use_case: UnderwriterCardDep
) -> UnderwriterCard:
    return UnderwriterCard.model_validate(await use_case.execute(application_id))


@router.get("/metrics", response_model=BackofficeMetricsDTO)
async def metrics(
    _: CanReadBackoffice,
    use_case: BackofficeMetricsDep,
    date_from: date | None = None,
    date_to: date | None = None,
) -> BackofficeMetricsDTO:
    """By days and products; the last 30 days by default."""
    return await use_case.execute(date_from, date_to)
