from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from src.core.access.dependencies import require_permissions
from src.core.access.permissions import Permissions
from src.modules.bff.application.dto.applications_overview import ApplicationsOverviewDTO
from src.modules.bff.application.dto.scoring_overview import ScoringOverviewDTO
from src.modules.bff.presentation.dependencies import (
    ApplicationsOverviewDep,
    BackofficeMetricsDep,
    CanReadBackoffice,
    ScoringOverviewDep,
    UnderwriterCardDep,
    UnderwritingQueueDep,
)
from src.modules.bff.presentation.schemas.backoffice import UnderwriterCard
from src.modules.projector.facade import (
    BackofficeMetricsDTO,
    QueuePageDTO,
    QueueSort,
    ReviewKind,
)

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
    review: Annotated[
        ReviewKind | None,
        Query(
            description="check — проверка (модели видят умеренный риск), dispute — спорная "
            "(модели или данные расходятся); не задан — все. `total` — по фильтру."
        ),
    ] = None,
) -> QueuePageDTO:
    return await use_case.execute(status, sort, limit, offset, review)


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


@router.get(
    "/scoring-overview",
    response_model=ScoringOverviewDTO,
    dependencies=[Depends(require_permissions(Permissions.SCORING_READ))],
)
async def scoring_overview(
    _: CanReadBackoffice,
    use_case: ScoringOverviewDep,
    limit: Annotated[int, Query(ge=1, le=200, description="How many latest applications")] = 50,
) -> ScoringOverviewDTO:
    """Scoring over the submitted applications in one call: counts over the latest 1000 of
    them (`considered`) — scored, stopped before the models, models agree by zone, incomplete
    data, sent to an underwriter, decided automatically; grades of both models, the zone
    matrix, model and policy versions; and the latest `limit` applications with both grades
    and the decision."""
    return await use_case.execute(limit)


@router.get(
    "/applications-overview",
    response_model=ApplicationsOverviewDTO,
    dependencies=[Depends(require_permissions(Permissions.REQUESTS_READ))],
)
async def applications_overview(
    _: CanReadBackoffice,
    use_case: ApplicationsOverviewDep,
    latest: Annotated[int, Query(ge=0, le=50, description="How many latest applications")] = 10,
) -> ApplicationsOverviewDTO:
    """Every company's applications in one call, counted by the database: the funnel (how far
    they got: started, submitted, decided, approved, signed, disbursed), statuses, products
    and requested amounts, amount buckets (up to 1, 1–3, 3–10, 10–30, 30+ mln) and the latest
    `latest` applications with the company name."""
    return await use_case.execute(latest)
