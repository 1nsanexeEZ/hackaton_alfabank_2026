"""The client's screens: the list of applications and the company dashboard."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from src.modules.projector.domain.enums import ActionRequired


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
class ApplicationGroupDTO:
    """Applications of one status and product: how many and the requested amount."""

    status: str
    product_code: str
    product_name: str
    count: int
    amount: Decimal  # sum of the requested amounts, 0 without them


@dataclass(frozen=True, slots=True)
class AmountBucketDTO:
    """Applications with a requested amount from `min` (inclusive) to `max` (exclusive)."""

    min: Decimal
    max: Decimal | None  # None — no upper bound
    count: int


@dataclass(frozen=True, slots=True)
class LatestApplicationDTO:
    application_id: UUID
    organization_id: UUID
    number: str
    company_name: str
    inn: str
    product_code: str
    product_name: str
    amount: Decimal | None
    status: str
    client_stage: str | None
    submitted_at: datetime | None
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ApplicationStatsDTO:
    """Over every application of every company, drafts too."""

    groups: tuple[ApplicationGroupDTO, ...]
    amount_buckets: tuple[AmountBucketDTO, ...]
    latest: tuple[LatestApplicationDTO, ...]


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
