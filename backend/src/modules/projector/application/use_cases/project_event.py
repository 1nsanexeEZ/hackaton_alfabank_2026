"""Applying an event to the read models — the only projection code: the live
consumer and the rebuild both call ProjectEventUseCase.execute().

An event is a signal. The current state is read from the owning modules
through their facades and stored with its version, history (timeline, the
moment of the first decision) is taken from the event itself. Every step is an
upsert or a recomputation, so a repeated, late or reordered event leaves the
same rows as the original order.
"""

import logging
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from src.core.exceptions.exceptions import NotFoundError
from src.core.messaging.contracts.base import IntegrationMessage
from src.core.messaging.contracts.decision import DecisionMade
from src.core.messaging.contracts.process import UserTaskCompleted, UserTaskCreated
from src.core.messaging.envelope import Envelope
from src.modules.applications.facade import ACTIVE_STATUSES, ApplicationCardDTO, ApplicationsFacade
from src.modules.clients.facade import ClientsFacade
from src.modules.decision.facade import DecisionFacade
from src.modules.process.facade import ProcessFacade, UserTaskDTO
from src.modules.products.facade import ProductsFacade
from src.modules.projector.application.interfaces.neighbours import FacadeLookup
from src.modules.projector.application.interfaces.repositories import ReadModelStore
from src.modules.projector.application.mappers.timeline import timeline_entry
from src.modules.projector.domain.metrics import DailyMetrics
from src.modules.projector.domain.read_models import (
    MANUAL_REVIEW,
    ApplicationOverview,
    OrganizationDashboard,
    QueueItem,
    action_required,
    has_cash_gap,
    task_stage,
)
from src.modules.scoring.facade import ScoringFacade, ScoringResultDTO

logger = logging.getLogger(__name__)

# Facades already reported as missing, so the log is not flooded on every event.
_reported_missing: set[str] = set()


def as_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


class ProjectEventUseCase:
    def __init__(self, store: ReadModelStore, facades: FacadeLookup) -> None:
        self._store = store
        self._facades = facades
        self._product_names: dict[str, str] = {}

    async def execute(self, envelope: Envelope, message: IntegrationMessage) -> None:
        at = as_utc(envelope.occurred_at)
        application_id = getattr(message, "application_id", None)
        if isinstance(application_id, UUID):
            await self._apply_to_application(application_id, envelope.event_id, at, message)
            return
        organization_id = getattr(message, "organization_id", None)
        if isinstance(organization_id, UUID):
            await self._refresh_dashboard(organization_id, at)

    # --- application ----------------------------------------------------------

    async def _apply_to_application(
        self, application_id: UUID, event_id: UUID, at: datetime, message: IntegrationMessage
    ) -> None:
        overview = await self._store.get_overview(application_id)
        cells = overview.metric_cells() if overview is not None else set()
        overview = await self._refresh_overview(application_id, overview)
        if overview is not None:
            if isinstance(message, DecisionMade):
                overview.record_decision(message.outcome, message.decided_by, at)
            await self._store.save_overview(overview)

        if isinstance(message, UserTaskCreated | UserTaskCompleted):
            await self._note_task(message, at)
        await self._refresh_queue(application_id, overview)

        entry = timeline_entry(event_id, at, message)
        if entry is not None:
            await self._store.add_timeline_entry(entry)

        if overview is not None:
            for day, product_code in sorted(cells | overview.metric_cells()):
                rows = await self._store.overviews_for_metrics(day, product_code)
                await self._store.save_metrics(DailyMetrics.compute(day, product_code, rows))
        organization_id = (
            overview.organization_id
            if overview is not None
            else getattr(message, "organization_id", None)
        )
        if isinstance(organization_id, UUID):
            await self._refresh_dashboard(organization_id, at)

    async def _refresh_overview(
        self, application_id: UUID, current: ApplicationOverview | None
    ) -> ApplicationOverview | None:
        applications = self._optional(ApplicationsFacade)  # type: ignore[type-abstract]
        if applications is None:
            return current
        try:
            card = await applications.get_card(application_id)
        except NotFoundError:
            logger.warning("Application %s is unknown to the applications module", application_id)
            return current
        fresh = await self._overview_from_card(card)
        if current is None:
            return fresh
        current.take_card(fresh)
        return current

    async def _overview_from_card(self, card: ApplicationCardDTO) -> ApplicationOverview:
        company_name, inn = await self._company(card)
        return ApplicationOverview(
            application_id=card.id,
            organization_id=card.organization_id,
            number=card.number,
            product_code=card.product_code,
            product_name=await self._product_name(card.product_code),
            company_name=company_name,
            inn=inn,
            amount=card.request.amount if card.request else None,
            term_months=card.request.term_months if card.request else None,
            status=card.status,
            client_stage=card.client_stage,
            action_required=action_required(card.status),
            offer_amount=card.offer.amount if card.offer else None,
            offer_rate=card.offer.rate if card.offer else None,
            submitted_at=as_utc(card.submitted_at) if card.submitted_at else None,
            updated_at=as_utc(card.updated_at),
            source_version=card.version,
        )

    async def _company(self, card: ApplicationCardDTO) -> tuple[str, str]:
        """Name and INN frozen at submission; a draft has no snapshot yet."""
        if card.org_snapshot is not None:
            return card.org_snapshot.name, card.org_snapshot.inn
        clients = self._optional(ClientsFacade)  # type: ignore[type-abstract]
        if clients is None:
            return "", ""
        try:
            snapshot = await clients.get_snapshot(card.organization_id)
        except NotFoundError:
            return "", ""
        return snapshot.name, snapshot.inn

    async def _product_name(self, code: str) -> str:
        if code not in self._product_names:
            products = self._optional(ProductsFacade)  # type: ignore[type-abstract]
            name = code
            if products is not None:
                try:
                    name = (await products.get_product(code)).name
                except NotFoundError:
                    pass
            self._product_names[code] = name
        return self._product_names[code]

    # --- underwriting queue -----------------------------------------------------

    async def _note_task(self, message: UserTaskCreated | UserTaskCompleted, at: datetime) -> None:
        """Make sure the task has a row even if process cannot tell more about it."""
        current = await self._store.get_queue_item(message.task_id)
        if isinstance(message, UserTaskCreated):
            if current is None:
                await self._store.save_queue_item(
                    QueueItem(
                        task_id=message.task_id,
                        application_id=message.application_id,
                        task_type=message.task_type,
                        candidate_role=message.candidate_role,
                        status="open",
                        assignee_id=None,
                        due_at=as_utc(message.due_at) if message.due_at else None,
                        created_at=at,
                        source_version=task_stage("open"),
                    )
                )
            return
        if current is not None and task_stage(current.status) < task_stage("done"):
            current.status = "done"
            current.source_version = task_stage("done")
            await self._store.save_queue_item(current)

    async def _refresh_queue(
        self, application_id: UUID, overview: ApplicationOverview | None
    ) -> None:
        items = await self._store.queue_items_of(application_id)
        if not items:
            return
        scoring = await self._scoring_result(application_id)
        reasons = await self._routing_reasons(application_id)
        for item in items:
            task = await self._task(item.task_id)
            if task is not None:
                item.take_task(_queue_item_from_task(task))
            if overview is not None:
                item.take_application(overview)
            item.score = scoring.score if scoring else None
            item.risk_grade = scoring.grade if scoring else None
            item.cash_gap = has_cash_gap(scoring.flags) if scoring else False
            item.routing_reasons = reasons
            await self._store.save_queue_item(item)

    async def _task(self, task_id: UUID) -> UserTaskDTO | None:
        process = self._optional(ProcessFacade)  # type: ignore[type-abstract]
        return await process.get_task(task_id) if process is not None else None

    async def _scoring_result(self, application_id: UUID) -> ScoringResultDTO | None:
        scoring = self._optional(ScoringFacade)  # type: ignore[type-abstract]
        return await scoring.get_result(application_id) if scoring is not None else None

    async def _routing_reasons(self, application_id: UUID) -> tuple[str, ...]:
        """Why the application waits for an underwriter: reason codes of the
        current decision while it is MANUAL_REVIEW (a function of the current
        state, so the rebuild restores it as well)."""
        decisions = self._optional(DecisionFacade)  # type: ignore[type-abstract]
        if decisions is None:
            return ()
        decision = await decisions.get_decision(application_id)
        if decision is None or decision.outcome != MANUAL_REVIEW:
            return ()
        return tuple(decision.reason_codes)

    # --- organization dashboard ---------------------------------------------------

    async def _refresh_dashboard(self, organization_id: UUID, at: datetime) -> None:
        dashboard = await self._store.get_dashboard(organization_id) or OrganizationDashboard(
            organization_id
        )
        active, waiting = await self._store.count_applications(organization_id, ACTIVE_STATUSES)
        dashboard.active_applications = active
        dashboard.action_required_count = waiting
        offers = await self._pre_approved(organization_id)
        if offers is not None:
            dashboard.pre_approved_max_amount = max((amount for amount, _ in offers), default=None)
            dashboard.pre_approved_rate_from = min((rate for _, rate in offers), default=None)
        dashboard.touch(at)
        await self._store.save_dashboard(dashboard)

    async def _pre_approved(self, organization_id: UUID) -> list[tuple[Decimal, Decimal]] | None:
        decisions = self._optional(DecisionFacade)  # type: ignore[type-abstract]
        if decisions is None:
            return None
        offers = await decisions.get_pre_approved(organization_id)
        return [(offer.max_amount, offer.rate_from) for offer in offers]

    # --- helpers ------------------------------------------------------------------

    def _optional[T](self, key: type[T]) -> T | None:
        """A neighbour that is not wired yet only makes the rows poorer, it
        does not stop the projection (and every other consumer of the topic).
        FacadeNotRegisteredError is a LookupError; core.facades itself is out
        of reach of the application layer."""
        try:
            return self._facades(key)
        except LookupError:
            if key.__name__ not in _reported_missing:
                _reported_missing.add(key.__name__)
                logger.warning("Projector works without %s: it is not registered", key.__name__)
            return None


def _queue_item_from_task(task: UserTaskDTO) -> QueueItem:
    return QueueItem(
        task_id=task.id,
        application_id=task.application_id,
        task_type=task.type,
        candidate_role=task.candidate_role,
        status=task.status,
        assignee_id=task.assignee_id,
        due_at=as_utc(task.due_at) if task.due_at else None,
        created_at=as_utc(task.created_at),
        source_version=task_stage(task.status),
    )
