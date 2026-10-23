"""The underwriting queue."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID


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
    # check or dispute, by the routing reasons (decision `review_kind`).
    review: Literal["check", "dispute"] | None = None


@dataclass(frozen=True, slots=True)
class QueuePageDTO:
    items: tuple[QueueItemDTO, ...]
    total: int
