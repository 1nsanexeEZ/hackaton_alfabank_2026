"""Enrichment contract: what external sources and bank statements said about
the company at the time of the application."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Protocol
from uuid import UUID

Source = Literal["egrul", "fns", "bki", "statement", "gir_bo", "kontur", "bki_head"]


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
    # Дата записи о нынешнем руководителе; None — реестр её не сообщил (снимки до неё).
    head_since: date | None = None


@dataclass(frozen=True, slots=True)
class AccountBlockDTO:
    """Решение ФНС о приостановлении операций по счетам."""

    decision_number: str
    date: date
    authority_code: str
    reason: str


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
    account_blocks: tuple[AccountBlockDTO, ...] = ()


@dataclass(frozen=True, slots=True)
class AccountingPeriodDTO:
    """Год бухотчётности из ГИР БО, рубли (у источника — тыс. ₽)."""

    year: int
    revenue: Decimal
    cost_of_sales: Decimal
    sales_profit: Decimal
    interest_payable: Decimal
    net_profit: Decimal
    fixed_assets: Decimal
    inventories: Decimal
    receivables: Decimal
    cash: Decimal
    equity: Decimal
    total_assets: Decimal
    long_term_liabilities: Decimal
    short_term_liabilities: Decimal
    total_liabilities: Decimal  # строка 1700 — итог пассива


@dataclass(frozen=True, slots=True)
class AccountingReportsDTO:
    available: bool
    reason: str | None  # почему отчётности нет: ИП, компания младше года
    periods: tuple[AccountingPeriodDTO, ...]  # от старых к новым

    @property
    def latest(self) -> AccountingPeriodDTO | None:
        return max(self.periods, key=lambda p: p.year) if self.periods else None


@dataclass(frozen=True, slots=True)
class ArbitrationDTO:
    as_defendant: int
    as_plaintiff: int
    defendant_sum: Decimal  # иски к компании, рубли


@dataclass(frozen=True, slots=True)
class EnforcementDTO:
    active: int
    sum: Decimal


@dataclass(frozen=True, slots=True)
class BankruptcyMessageDTO:
    date: date
    type: str
    case: str


@dataclass(frozen=True, slots=True)
class GovContractsDTO:
    count: int
    sum: Decimal


@dataclass(frozen=True, slots=True)
class CounterpartyRiskDTO:
    """Контур.Фокус: суды, приставы, банкротство."""

    reliability: Literal["green", "yellow", "red"]
    notes: tuple[str, ...]
    arbitration: ArbitrationDTO
    enforcement: EnforcementDTO
    bankruptcy_messages: tuple[BankruptcyMessageDTO, ...]
    gov_contracts: GovContractsDTO
    active_pledges: int


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
    gir_bo: AccountingReportsDTO | None = None
    kontur: CounterpartyRiskDTO | None = None
    # Кредитная история руководителя по реестру — только с его личным согласием.
    bki_head: CreditHistoryDTO | None = None
    # Не запрошенные источники и почему: no_consent, no_head.
    sources_skipped: tuple[SourceErrorDTO, ...] = ()


class EnrichmentFacade(Protocol):
    async def get_snapshot(self, application_id: UUID) -> EnrichmentSnapshotDTO | None: ...

    async def lookup_registry(self, inn: str) -> RegistryExtractDTO | None: ...
