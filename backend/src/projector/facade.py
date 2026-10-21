"""Projector contract: denormalized read models for lists, queues and
dashboards. No access checks inside — bff checks rights before calling."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal, Protocol
from uuid import UUID

ActionRequired = Literal["none", "info", "offer", "sign"]
Audience = Literal["client", "bank"]
QueueSort = Literal["due_at", "amount", "score", "created_at"]


@dataclass(frozen=True, slots=True)
class ApplicationOverviewDTO:
    application_id: UUID
    organization_id: UUID
    number: str
    product_code: str
    product_name: str
    amount: Decimal | None
    term_months: int | None
    status: str
    client_stage: str | None
    action_required: ActionRequired
    offer_amount: Decimal | None
    offer_rate: Decimal | None
    submitted_at: datetime | None
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ApplicationPageDTO:
    items: tuple[ApplicationOverviewDTO, ...]
    total: int


@dataclass(frozen=True, slots=True)
class OrganizationDashboardDTO:
    organization_id: UUID
    active_applications: int
    action_required_count: int
    pre_approved_max_amount: Decimal | None
    pre_approved_rate_from: Decimal | None
    last_activity_at: datetime | None


@dataclass(frozen=True, slots=True)
class QueueItemDTO:
    task_id: UUID
    application_id: UUID
    number: str
    company_name: str
    inn: str
    product_code: str
    amount: Decimal | None
    score: int | None
    risk_grade: str | None
    cash_gap: bool
    routing_reasons: tuple[str, ...]
    due_at: datetime | None
    overdue: bool
    assignee_id: UUID | None
    status: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class QueuePageDTO:
    items: tuple[QueueItemDTO, ...]
    total: int


@dataclass(frozen=True, slots=True)
class TimelineEntryDTO:
    id: UUID
    application_id: UUID
    at: datetime
    kind: Literal["status", "stage", "task", "decision"]
    title: str
    audience: Audience
    details: dict[str, Any]


@dataclass(frozen=True, slots=True)
class DailyMetricsDTO:
    day: date
    product_code: str
    submitted: int
    approved: int
    counter_offers: int
    rejected: int
    manual_reviews: int
    auto_decisions: int
    avg_time_to_decision_sec: float | None


@dataclass(frozen=True, slots=True)
class BackofficeMetricsDTO:
    date_from: date
    date_to: date
    rows: tuple[DailyMetricsDTO, ...]
    submitted: int
    decided: int
    auto_decision_share: float | None
    avg_time_to_decision_sec: float | None


class ProjectorFacade(Protocol):
    async def list_applications(
        self,
        organization_id: UUID,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> ApplicationPageDTO: ...

    async def get_organization_dashboard(
        self, organization_id: UUID
    ) -> OrganizationDashboardDTO | None: ...

    async def get_underwriting_queue(
        self,
        role: str,
        status: str = "open",
        sort: QueueSort = "due_at",
        limit: int = 20,
        offset: int = 0,
    ) -> QueuePageDTO: ...

    async def get_timeline(
        self, application_id: UUID, audience: Audience
    ) -> list[TimelineEntryDTO]:
        """audience=client returns client entries only; bank gets everything."""
        ...

    async def get_backoffice_metrics(
        self, date_from: date, date_to: date
    ) -> BackofficeMetricsDTO: ...
