"""SQLAlchemy models of projector. Tables are prefixed with `projector_`.

Column names repeat the fields of the domain records (`domain/read_models.py`,
`domain/timeline.py`, `domain/metrics.py`): the repository copies them by name.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import BigInteger, Date, DateTime, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from src.core.infrastructure.database.base import Base, JSONType
from src.core.infrastructure.database.mixins import OrganizationOwnedMixin

MONEY = Numeric(18, 2)
RATE = Numeric(7, 4)


class ApplicationOverviewRow(OrganizationOwnedMixin, Base):
    """One row per application: the client's list and the source of the metrics."""

    __tablename__ = "projector_application_overview"
    __table_args__ = (
        Index("ix_projector_application_overview_org_updated_at", "organization_id", "updated_at"),
        Index("ix_projector_application_overview_org_status", "organization_id", "status"),
    )

    application_id: Mapped[UUID] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(32))
    product_code: Mapped[str] = mapped_column(String(64))
    product_name: Mapped[str] = mapped_column(String(255))
    company_name: Mapped[str] = mapped_column(String(255))
    inn: Mapped[str] = mapped_column(String(12))
    amount: Mapped[Decimal | None] = mapped_column(MONEY)
    term_months: Mapped[int | None]
    status: Mapped[str] = mapped_column(String(32))
    client_stage: Mapped[str | None] = mapped_column(String(255))
    action_required: Mapped[str] = mapped_column(String(16))
    offer_amount: Mapped[Decimal | None] = mapped_column(MONEY)
    offer_rate: Mapped[Decimal | None] = mapped_column(RATE)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source_version: Mapped[int]
    decision_outcome: Mapped[str | None] = mapped_column(String(32))
    decided_by: Mapped[str | None] = mapped_column(String(16))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    manual_review_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    time_to_decision_sec: Mapped[int | None]


class UnderwritingQueueRow(Base):
    """One row per user task of the process, open or closed."""

    __tablename__ = "projector_underwriting_queue"
    __table_args__ = (
        Index("ix_projector_underwriting_queue_role_due_at", "candidate_role", "status", "due_at"),
        Index("ix_projector_underwriting_queue_role_amount", "candidate_role", "status", "amount"),
        Index("ix_projector_underwriting_queue_role_score", "candidate_role", "status", "score"),
        Index(
            "ix_projector_underwriting_queue_role_created_at",
            "candidate_role",
            "status",
            "created_at",
        ),
    )

    task_id: Mapped[UUID] = mapped_column(primary_key=True)
    application_id: Mapped[UUID] = mapped_column(index=True)
    task_type: Mapped[str] = mapped_column(String(64))
    candidate_role: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32))
    assignee_id: Mapped[UUID | None]
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source_version: Mapped[int]
    number: Mapped[str] = mapped_column(String(32))
    company_name: Mapped[str] = mapped_column(String(255))
    inn: Mapped[str] = mapped_column(String(12))
    product_code: Mapped[str] = mapped_column(String(64))
    amount: Mapped[Decimal | None] = mapped_column(MONEY)
    score: Mapped[int | None]
    risk_grade: Mapped[str | None] = mapped_column(String(8))
    cash_gap: Mapped[bool]
    routing_reasons: Mapped[list[str]] = mapped_column(JSONType)


class TimelineEntryRow(Base):
    __tablename__ = "projector_application_timeline"
    __table_args__ = (
        Index("ix_projector_application_timeline_application_at", "application_id", "at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    application_id: Mapped[UUID]
    # One entry per event: a replay finds it and writes nothing.
    source_event_id: Mapped[UUID] = mapped_column(unique=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    kind: Mapped[str] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(String(500))
    audience: Mapped[str] = mapped_column(String(16))
    details: Mapped[dict[str, Any]] = mapped_column(JSONType)


class OrganizationDashboardRow(Base):
    __tablename__ = "projector_organization_dashboard"

    organization_id: Mapped[UUID] = mapped_column(primary_key=True)
    active_applications: Mapped[int]
    action_required_count: Mapped[int]
    pre_approved_max_amount: Mapped[Decimal | None] = mapped_column(MONEY)
    pre_approved_rate_from: Mapped[Decimal | None] = mapped_column(RATE)
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BackofficeMetricsRow(Base):
    """Counters of one product for one UTC day."""

    __tablename__ = "projector_backoffice_metrics"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    product_code: Mapped[str] = mapped_column(String(64), primary_key=True)
    submitted: Mapped[int]
    approved: Mapped[int]
    counter_offers: Mapped[int]
    rejected: Mapped[int]
    manual_reviews: Mapped[int]
    auto_decisions: Mapped[int]
    decision_time_total_sec: Mapped[int] = mapped_column(BigInteger)
    decision_time_count: Mapped[int]
