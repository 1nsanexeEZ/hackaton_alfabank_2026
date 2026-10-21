from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from src.bff.api.dependencies import BackofficeScreensDep, CanReadBackoffice, Today
from src.bff.application import views
from src.core.access.dependencies import require_permissions
from src.core.access.permissions import Permissions
from src.projector.facade import BackofficeMetricsDTO, QueuePageDTO, QueueSort

router = APIRouter(prefix="/bff/backoffice", tags=["bff"])


@router.get(
    "/queue",
    response_model=QueuePageDTO,
    dependencies=[Depends(require_permissions(Permissions.TASKS_READ))],
)
async def underwriting_queue(
    _: CanReadBackoffice,
    screens: BackofficeScreensDep,
    # open — waiting for a person (taken tasks too), closed — done or cancelled.
    status: Literal["open", "closed", "in_progress", "done", "cancelled"] = "open",
    sort: QueueSort = "due_at",
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> QueuePageDTO:
    return await screens.queue(status, sort, limit, offset)


@router.get(
    "/applications/{application_id}",
    response_model=views.UnderwriterCard,
    dependencies=[Depends(require_permissions(Permissions.DECISIONS_READ))],
)
async def underwriter_card(
    application_id: UUID, _: CanReadBackoffice, screens: BackofficeScreensDep
) -> views.UnderwriterCard:
    return await screens.application(application_id)


@router.get("/metrics", response_model=BackofficeMetricsDTO)
async def metrics(
    _: CanReadBackoffice,
    screens: BackofficeScreensDep,
    today: Today,
    date_from: date | None = None,
    date_to: date | None = None,
) -> BackofficeMetricsDTO:
    """By days and products; the last 30 days by default."""
    return await screens.metrics(today, date_from, date_to)
