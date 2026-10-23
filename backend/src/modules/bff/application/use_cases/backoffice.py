"""Back office screens: underwriter queue, underwriter card, pipeline metrics.

The queue and the metrics are one projector query each. The card takes the
application from its owner and everything the bank knows about it: the
enrichment snapshot with the cash flow forecast, scoring factors, the full
decision with its rule trace, the bank timeline and where the process is; for a
startup — the project assessment made before the application with the form
filled in from it."""

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from src.core.domain.clock import Clock
from src.core.exceptions.exceptions import ValidationError
from src.modules.applications.facade import ApplicationCardDTO, ApplicationsFacade
from src.modules.bff.application.dto.backoffice import StartupProjectDTO, UnderwriterCardDTO
from src.modules.bff.application.interfaces.neighbours import Neighbours
from src.modules.bff.application.use_cases.common import segment_of
from src.modules.bff.domain.client_status import client_status
from src.modules.bff.domain.project_form import project_form
from src.modules.clients.facade import ClientsFacade
from src.modules.decision.facade import DecisionFacade
from src.modules.enrichment.facade import EnrichmentFacade
from src.modules.process.facade import ProcessFacade, UserTaskDTO
from src.modules.products.facade import ProductsFacade
from src.modules.projector.facade import (
    BackofficeMetricsDTO,
    ProjectorFacade,
    QueuePageDTO,
    QueueSort,
    TimelineEntryDTO,
)
from src.modules.scoring.facade import ScoringFacade

UNDERWRITER_ROLE = "underwriter"
METRICS_DEFAULT_DAYS = 30
METRICS_MAX_DAYS = 366
# Open tasks scanned to find the one of the application: the process facade
# looks tasks up by role, and the open queue is short.
_OPEN_TASKS_SCAN = 500


class UnderwritingQueueUseCase:
    def __init__(self, neighbours: Neighbours) -> None:
        self._n = neighbours

    async def execute(self, status: str, sort: QueueSort, limit: int, offset: int) -> QueuePageDTO:
        return await self._n(ProjectorFacade).get_underwriting_queue(
            UNDERWRITER_ROLE, status, sort, limit, offset
        )


class BackofficeMetricsUseCase:
    """By days and products; the last 30 days by default."""

    def __init__(self, neighbours: Neighbours, clock: Clock) -> None:
        self._n = neighbours
        self._clock = clock

    async def execute(self, date_from: date | None, date_to: date | None) -> BackofficeMetricsDTO:
        date_to = date_to or self._clock.now().date()
        date_from = date_from or date_to - timedelta(days=METRICS_DEFAULT_DAYS - 1)
        if date_from > date_to:
            raise ValidationError("date_from is after date_to")
        if (date_to - date_from).days >= METRICS_MAX_DAYS:
            raise ValidationError(f"The period is longer than {METRICS_MAX_DAYS} days")
        return await self._n(ProjectorFacade).get_backoffice_metrics(date_from, date_to)


class UnderwriterCardUseCase:
    def __init__(self, neighbours: Neighbours) -> None:
        self._n = neighbours

    async def execute(self, application_id: UUID) -> UnderwriterCardDTO:
        card = await self._n(ApplicationsFacade).get_card(application_id)
        enrichment = await self._n.optional(
            "enrichment", lambda: self._n(EnrichmentFacade).get_snapshot(application_id), None
        )
        scoring = await self._n.optional(
            "scoring", lambda: self._n(ScoringFacade).get_result(application_id), None
        )
        decision = await self._n.optional(
            "decision", lambda: self._n(DecisionFacade).get_decision(application_id), None
        )
        product_fit = await self._n.optional(
            "product_fit",
            lambda: self._n(ProductsFacade).check_eligibility(
                card.product_code, card.organization_id
            ),
            None,
        )
        timeline: list[TimelineEntryDTO] = await self._n.optional(
            "timeline", lambda: self._n(ProjectorFacade).get_timeline(application_id, "bank"), []
        )
        process = await self._n.optional(
            "process", lambda: self._n(ProcessFacade).get_process_view(application_id), None
        )
        task = await self._n.optional("task", lambda: self._open_task(application_id), None)
        startup = None
        # A company without turnover: the bank assessed its project before the application.
        if card.org_snapshot is not None and segment_of(card.org_snapshot) == "startup":
            startup = await self._n.optional("startup", lambda: self._startup(card), None)
        return UnderwriterCardDTO(
            application=card,
            client_status=client_status(
                card.status, card.client_stage, card.offer.kind if card.offer else None
            ),
            enrichment=enrichment,
            scoring=scoring,
            decision=decision,
            product_fit=product_fit,
            timeline=tuple(timeline),
            process=process,
            task=task,
            degraded=self._n.degraded,
            startup=startup,
        )

    async def _startup(self, card: ApplicationCardDTO) -> StartupProjectDTO | None:
        assessment = await self._n(DecisionFacade).get_project_assessment(card.organization_id)
        if assessment is None or assessment.product_code != card.product_code:
            return None
        plan = await self._n(ClientsFacade).get_business_plan(card.organization_id)
        model = plan.financial_model if plan is not None else None
        submitted = card.submitted_at
        valid = assessment.status == "passed" and (
            assessment.checked_at <= submitted <= assessment.valid_until
            if submitted is not None
            else assessment.valid
        )
        request = card.request
        return StartupProjectDTO(
            assessment=assessment,
            business_plan=plan,
            plan_changed=plan is not None and plan.revision != assessment.plan_revision,
            valid_at_submission=valid,
            form=project_form(
                passed=valid,
                pre_approved=assessment.max_amount,
                requested=request.amount if request is not None else None,
                term_months=request.term_months if request is not None else None,
                collateral_description=model.collateral_description if model else None,
                guarantee=model.guarantee if model else "none",
                guarantee_share=model.guarantee_share if model else Decimal(0),
            ),
        )

    async def _open_task(self, application_id: UUID) -> UserTaskDTO | None:
        tasks = await self._n(ProcessFacade).list_open_tasks(
            UNDERWRITER_ROLE, limit=_OPEN_TASKS_SCAN
        )
        return next((t for t in tasks if t.application_id == application_id), None)
