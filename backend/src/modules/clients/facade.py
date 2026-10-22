"""Clients contract for other modules: who the borrower is and who may act for it."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal, Protocol
from uuid import UUID

LegalForm = Literal["LLC", "IE", "JSC"]
MemberRole = Literal["owner", "director", "accountant", "employee"]
VerificationStatus = Literal["unverified", "verified", "mismatch"]
RegistryStatus = Literal["active", "liquidating", "liquidated", "bankrupt"]
ReportSource = Literal["declared", "fns", "bank_statement"]


class OrgPermission(StrEnum):
    """Rights inside a company (not to be confused with token permissions)."""

    VIEW = "view"
    SUBMIT_APPLICATION = "submit_application"
    SIGN = "sign"
    MANAGE_MEMBERS = "manage_members"
    EDIT_FINANCIALS = "edit_financials"


@dataclass(frozen=True, slots=True)
class DiscrepancyDTO:
    field: str
    declared: str | None
    registry: str | None


@dataclass(frozen=True, slots=True)
class FinancialReportDTO:
    period_year: int
    period_quarter: int | None
    source: ReportSource
    revenue: Decimal
    expenses: Decimal | None = None
    net_profit: Decimal | None = None
    total_liabilities: Decimal | None = None
    monthly_debt_payments: Decimal | None = None


@dataclass(frozen=True, slots=True)
class OrganizationSnapshotDTO:
    id: UUID
    inn: str
    ogrn: str
    kpp: str | None
    legal_form: LegalForm
    name: str
    registered_at: date
    business_age_months: int
    okved_main: str
    okved_extra: tuple[str, ...]
    region_code: str
    tax_regime: str
    employees_count: int
    registry_status: RegistryStatus
    verification_status: VerificationStatus
    discrepancies: tuple[DiscrepancyDTO, ...]
    head_name: str | None
    # Up to two latest annual reports, newest first.
    financial_reports: tuple[FinancialReportDTO, ...]
    snapshot_at: datetime


@dataclass(frozen=True, slots=True)
class OrganizationSummaryDTO:
    id: UUID
    name: str
    inn: str
    legal_form: LegalForm
    my_role: MemberRole
    my_permissions: frozenset[str]


class ClientsFacade(Protocol):
    async def ensure_can(self, account_id: UUID, organization_id: UUID, permission: str) -> None:
        """Raises PermissionDeniedError; a stranger to the company gets NotFoundError."""
        ...

    async def get_member_permissions(
        self, account_id: UUID, organization_id: UUID
    ) -> frozenset[str]: ...

    async def get_member_organization_ids(self, account_id: UUID) -> frozenset[UUID]: ...

    async def get_snapshot(self, organization_id: UUID) -> OrganizationSnapshotDTO: ...

    async def list_my_organizations(self, account_id: UUID) -> list[OrganizationSummaryDTO]: ...

    async def list_members(
        self, organization_id: UUID, permission: str | None = None
    ) -> list[UUID]: ...
