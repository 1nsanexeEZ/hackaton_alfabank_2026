"""Domain events of clients. The application layer maps them to
`clients.events` contracts before they go to the outbox."""

from dataclasses import dataclass
from uuid import UUID

from src.clients.domain.value_objects import Discrepancy
from src.core.domain import DomainEvent


@dataclass(frozen=True, kw_only=True)
class OrganizationEvent(DomainEvent):
    organization_id: UUID


@dataclass(frozen=True, kw_only=True)
class MemberAdded(OrganizationEvent):
    account_id: UUID
    role: str


@dataclass(frozen=True, kw_only=True)
class MemberRemoved(OrganizationEvent):
    account_id: UUID


@dataclass(frozen=True, kw_only=True)
class MemberRoleChanged(OrganizationEvent):
    account_id: UUID
    role: str
    previous_role: str


@dataclass(frozen=True, kw_only=True)
class OrganizationVerified(OrganizationEvent):
    pass


@dataclass(frozen=True, kw_only=True)
class OrganizationVerificationMismatch(OrganizationEvent):
    discrepancies: tuple[Discrepancy, ...]


@dataclass(frozen=True, kw_only=True)
class FinancialReportSubmitted(OrganizationEvent):
    report_id: UUID
    period_year: int
    period_quarter: int | None
    source: str
