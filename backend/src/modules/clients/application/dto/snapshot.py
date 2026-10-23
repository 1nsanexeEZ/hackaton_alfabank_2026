"""The company as other modules see it: requisites, registry data, the check
against the registry and the latest annual reports. Re-exported by facade.py."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

LegalForm = Literal["LLC", "IE", "JSC"]
VerificationStatus = Literal["unverified", "verified", "mismatch"]
RegistryStatus = Literal["active", "liquidating", "liquidated", "bankrupt"]
ReportSource = Literal["declared", "fns", "bank_statement"]


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
