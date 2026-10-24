from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Self
from uuid import UUID

from src.modules.bff.application.dto.applications import ApplicationRowDTO
from src.modules.bff.application.dto.organizations import (
    CurrentOrganizationDTO,
    OrganizationBriefDTO,
)
from src.modules.bff.domain.consents import ConsentInfo
from src.modules.bff.domain.enums import ConsentKind, ConsentScope, TodoKind
from src.modules.decision.facade import FounderPrescreenDTO, ProjectAssessmentDTO
from src.modules.identity.facade import ConsentDTO
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
class ConsentStateDTO:
    type: ConsentKind
    scope: ConsentScope
    title: str
    # What the consent lets the bank do.
    purpose: str
    # Without it an application cannot be submitted.
    required: bool
    # In force now: given, not revoked, not run out.
    given: bool
    given_at: datetime | None
    valid_until: datetime | None

    @classmethod
    def of(cls, info: ConsentInfo, consent: ConsentDTO | None) -> Self:
        return cls(
            type=info.type,
            scope=info.scope,
            title=info.title,
            purpose=info.purpose,
            required=info.required,
            given=consent is not None,
            given_at=consent.given_at if consent else None,
            valid_until=consent.valid_until if consent else None,
        )


@dataclass(frozen=True, slots=True)
class FeedDTO:
    unread: int
    items: tuple[FeedItemDTO, ...]


@dataclass(frozen=True, slots=True)
class StartupBlockDTO:
    # None — not run yet.
    prescreen: FounderPrescreenDTO | None
    # The business plan in the cabinet: None — not filled in yet.
    business_plan_revision: int | None = None
    # The bank's project assessment by the business plan; None — not run yet.
    project: ProjectAssessmentDTO | None = None


@dataclass(frozen=True, slots=True)
class DashboardDTO:
    # No companies yet: the frontend offers to add one.
    onboarding: bool
    organization: CurrentOrganizationDTO | None
    organizations: tuple[OrganizationBriefDTO, ...]
    counters: OrganizationDashboardDTO | None
    # A startup has no turnover to pre-approve on: only the offer by its project assessment.
    pre_approved: tuple[PreApprovedProductDTO, ...]
    active_applications: tuple[ApplicationRowDTO, ...]
    todo: tuple[TodoItemDTO, ...]
    # The consents asked for before an application: which are given, which are missing.
    consents: tuple[ConsentStateDTO, ...]
    feed: FeedDTO
    news: tuple[NewsItemDTO, ...]
    degraded: tuple[str, ...]
    # Only for organization.segment = startup.
    startup: StartupBlockDTO | None = None
