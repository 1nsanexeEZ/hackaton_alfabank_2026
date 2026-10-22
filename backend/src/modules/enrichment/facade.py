"""Enrichment contract: what external sources and bank statements said about
the company at the time of the application."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Protocol
from uuid import UUID

Source = Literal["egrul", "fns", "bki", "statement"]


@dataclass(frozen=True, slots=True)
class FounderDTO:
    name: str
    share_percent: Decimal


@dataclass(frozen=True, slots=True)
class RegistryExtractDTO:
    inn: str
    ogrn: str
    legal_form: str
    full_name: str
    status: str
    registered_at: date
    okved_main: str
    okved_extra: tuple[str, ...]
    head_last_name: str
    head_first_name: str
    head_middle_name: str | None
    head_position: str
    founders: tuple[FounderDTO, ...]
    address: str
    region_code: str
    mass_address: bool
    # None for an entrepreneur and in snapshots taken before it was stored.
    kpp: str | None = None


@dataclass(frozen=True, slots=True)
class TaxProfileDTO:
    tax_arrears: Decimal
    avg_headcount: int
    reported_revenue: Decimal | None
    reported_expenses: Decimal | None
    report_year: int | None
    tax_regime: str
    disqualified_head: bool
    in_msp_registry: bool


@dataclass(frozen=True, slots=True)
class ObligationDTO:
    creditor: str
    kind: str
    amount: Decimal
    balance: Decimal
    monthly_payment: Decimal
    opened_at: date
    closes_at: date | None
    overdue_days: int


@dataclass(frozen=True, slots=True)
class CreditHistoryDTO:
    obligations: tuple[ObligationDTO, ...]
    inquiries_last_30d: int
    has_active_overdue: bool
    max_overdue_days_12m: int
    total_monthly_payments: Decimal


@dataclass(frozen=True, slots=True)
class CashflowMonthDTO:
    month: str  # YYYY-MM
    inflow: Decimal
    outflow: Decimal
    net: Decimal
    balance: Decimal


@dataclass(frozen=True, slots=True)
class CashflowProjectionDTO:
    month: str  # YYYY-MM
    projected_balance: Decimal


@dataclass(frozen=True, slots=True)
class CashflowForecastDTO:
    months_history: tuple[CashflowMonthDTO, ...]
    forecast: tuple[CashflowProjectionDTO, ...]
    gap_detected: bool
    gap_month: str | None
    gap_amount: Decimal | None
    annual_inflow: Decimal
    revenue_confirmed: bool | None
    method: str
    statement_document_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class SourceErrorDTO:
    source: Source
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class EnrichmentSnapshotDTO:
    id: UUID
    application_id: UUID
    organization_id: UUID
    collected_at: datetime
    sources_ok: tuple[Source, ...]
    sources_failed: tuple[SourceErrorDTO, ...]
    egrul: RegistryExtractDTO | None
    fns: TaxProfileDTO | None
    bki: CreditHistoryDTO | None
    cashflow: CashflowForecastDTO | None


class EnrichmentFacade(Protocol):
    async def get_snapshot(self, application_id: UUID) -> EnrichmentSnapshotDTO | None: ...

    async def lookup_registry(self, inn: str) -> RegistryExtractDTO | None: ...
