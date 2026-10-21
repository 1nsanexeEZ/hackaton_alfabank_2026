"""Read models of the projector and the rules that keep them right no matter
how often and in which order events arrive.

Card fields are a copy of the current state of the owner module and carry its
version: an older read never rolls a row back. Facts taken from events (when
the first decision was made) are merged order-independently, so a replay or a
late event gives the same row.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

# --- application overview ---------------------------------------------------

_ACTION_BY_STATUS: dict[str, str] = {
    "info_requested": "info",
    "offer_ready": "offer",
    "signing": "sign",
}

# Outcomes that close the bank's part of the review.
FINAL_OUTCOMES: frozenset[str] = frozenset({"APPROVE", "COUNTER_OFFER", "REJECT"})
MANUAL_REVIEW = "MANUAL_REVIEW"


def action_required(status: str) -> str:
    """What the client has to do now: answer, look at the offer, sign."""
    return _ACTION_BY_STATUS.get(status, "none")


def day_of(moment: datetime) -> date:
    """Metrics are kept by UTC days."""
    return moment.astimezone(UTC).date()


# Fields refreshed from the application card on every event.
CARD_FIELDS: tuple[str, ...] = (
    "organization_id",
    "number",
    "product_code",
    "product_name",
    "company_name",
    "inn",
    "amount",
    "term_months",
    "status",
    "client_stage",
    "action_required",
    "offer_amount",
    "offer_rate",
    "submitted_at",
    "updated_at",
    "source_version",
)


@dataclass(slots=True)
class ApplicationOverview:
    application_id: UUID
    organization_id: UUID
    number: str
    product_code: str
    product_name: str
    company_name: str
    inn: str
    amount: Decimal | None
    term_months: int | None
    status: str
    client_stage: str | None
    action_required: str
    offer_amount: Decimal | None
    offer_rate: Decimal | None
    submitted_at: datetime | None
    updated_at: datetime
    # Version of the application card the row was built from.
    source_version: int
    # The first final decision and the first routing to an underwriter.
    decision_outcome: str | None = None
    decided_by: str | None = None
    decided_at: datetime | None = None
    manual_review_at: datetime | None = None
    time_to_decision_sec: int | None = None

    def take_card(self, fresh: "ApplicationOverview") -> bool:
        """Copy the card fields of `fresh` unless it was read from an older version."""
        if fresh.source_version < self.source_version:
            return False
        for name in CARD_FIELDS:
            setattr(self, name, getattr(fresh, name))
        self._update_time_to_decision()
        return True

    def record_decision(self, outcome: str, decided_by: str, at: datetime) -> bool:
        """The earliest final decision wins: replays and late events change nothing."""
        if outcome in FINAL_OUTCOMES:
            if self.decided_at is not None and (
                self.decided_at,
                self.decision_outcome or "",
                self.decided_by or "",
            ) <= (at, outcome, decided_by):
                return False
            self.decision_outcome = outcome
            self.decided_by = decided_by
            self.decided_at = at
        elif outcome == MANUAL_REVIEW:
            if self.manual_review_at is not None and self.manual_review_at <= at:
                return False
            self.manual_review_at = at
        else:
            return False
        self._update_time_to_decision()
        return True

    def metric_cells(self) -> set[tuple[date, str]]:
        """(day, product) cells of the back office metrics this row counts in."""
        moments = (self.submitted_at, self.decided_at, self.manual_review_at)
        return {(day_of(m), self.product_code) for m in moments if m is not None}

    def _update_time_to_decision(self) -> None:
        if self.decided_at is None or self.submitted_at is None:
            self.time_to_decision_sec = None
            return
        seconds = int((self.decided_at - self.submitted_at).total_seconds())
        self.time_to_decision_sec = max(seconds, 0)


# --- underwriting queue -----------------------------------------------------

OPEN_TASK_STATUSES: tuple[str, ...] = ("open", "in_progress")
CLOSED_TASK_STATUSES: tuple[str, ...] = ("done", "cancelled")
# A task only moves forward: open -> in_progress -> done | cancelled.
_TASK_STAGES: dict[str, int] = {"open": 0, "in_progress": 1, "done": 2, "cancelled": 2}


def task_stage(status: str) -> int:
    """Version of a task row: tasks carry no version, their lifecycle does."""
    return _TASK_STAGES.get(status, 0)


def queue_statuses(status: str) -> tuple[str, ...]:
    """`open` — everything still waiting for a person (taken tasks too),
    `closed` — done or cancelled, anything else — that exact status."""
    if status == "open":
        return OPEN_TASK_STATUSES
    if status == "closed":
        return CLOSED_TASK_STATUSES
    return (status,)


def has_cash_gap(flags: tuple[str, ...] | list[str]) -> bool:
    """Scoring marks a forecast cash gap with a `cash_gap…` flag."""
    return any(flag.lower().startswith("cash_gap") for flag in flags)


TASK_FIELDS: tuple[str, ...] = (
    "task_type",
    "candidate_role",
    "status",
    "assignee_id",
    "due_at",
    "created_at",
    "source_version",
)


@dataclass(slots=True)
class QueueItem:
    task_id: UUID
    application_id: UUID
    task_type: str
    candidate_role: str
    status: str
    assignee_id: UUID | None
    due_at: datetime | None
    created_at: datetime
    source_version: int
    number: str = ""
    company_name: str = ""
    inn: str = ""
    product_code: str = ""
    amount: Decimal | None = None
    score: int | None = None
    risk_grade: str | None = None
    cash_gap: bool = False
    routing_reasons: tuple[str, ...] = ()

    def take_task(self, fresh: "QueueItem") -> bool:
        """Copy the task fields of `fresh` unless its lifecycle stage is behind."""
        if fresh.source_version < self.source_version:
            return False
        for name in TASK_FIELDS:
            setattr(self, name, getattr(fresh, name))
        return True

    def take_application(self, overview: ApplicationOverview) -> None:
        self.number = overview.number
        self.company_name = overview.company_name
        self.inn = overview.inn
        self.product_code = overview.product_code
        self.amount = overview.amount

    def is_overdue(self, now: datetime) -> bool:
        return self.due_at is not None and self.status in OPEN_TASK_STATUSES and self.due_at < now


# --- organization dashboard -------------------------------------------------


@dataclass(slots=True)
class OrganizationDashboard:
    organization_id: UUID
    active_applications: int = 0
    action_required_count: int = 0
    pre_approved_max_amount: Decimal | None = None
    pre_approved_rate_from: Decimal | None = None
    last_activity_at: datetime | None = None

    def touch(self, at: datetime) -> None:
        if self.last_activity_at is None or at > self.last_activity_at:
            self.last_activity_at = at
