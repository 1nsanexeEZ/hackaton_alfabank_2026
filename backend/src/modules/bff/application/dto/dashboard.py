from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from src.modules.bff.application.dto.applications import ApplicationRowDTO
from src.modules.bff.application.dto.organizations import (
    CurrentOrganizationDTO,
    OrganizationBriefDTO,
)
from src.modules.bff.domain.enums import TodoKind
from src.modules.decision.facade import FounderPrescreenDTO
from src.modules.notifications.facade import FeedItemDTO, NewsItemDTO
from src.modules.projector.facade import OrganizationDashboardDTO


@dataclass(frozen=True, slots=True)
class PreApprovedProductDTO:
    product_code: str
    product_name: str | None
    max_amount: Decimal
    rate_from: Decimal
    term_max_months: int
    valid_until: date


@dataclass(frozen=True, slots=True)
class TodoItemDTO:
    application_id: UUID
    number: str
    kind: TodoKind
    title: str


@dataclass(frozen=True, slots=True)
class FeedDTO:
    unread: int
    items: tuple[FeedItemDTO, ...]


@dataclass(frozen=True, slots=True)
class StartupBlockDTO:
    # None — not run yet.
    prescreen: FounderPrescreenDTO | None


@dataclass(frozen=True, slots=True)
class DashboardDTO:
    # No companies yet: the frontend offers to add one.
    onboarding: bool
    organization: CurrentOrganizationDTO | None
    organizations: tuple[OrganizationBriefDTO, ...]
    counters: OrganizationDashboardDTO | None
    # Empty for a startup: there is no turnover to pre-approve on.
    pre_approved: tuple[PreApprovedProductDTO, ...]
    active_applications: tuple[ApplicationRowDTO, ...]
    todo: tuple[TodoItemDTO, ...]
    feed: FeedDTO
    news: tuple[NewsItemDTO, ...]
    degraded: tuple[str, ...]
    # Only for organization.segment = startup.
    startup: StartupBlockDTO | None = None
