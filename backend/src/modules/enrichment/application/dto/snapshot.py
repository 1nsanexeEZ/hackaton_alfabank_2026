"""Снимок обогащения по заявке — как его видят соседи (scoring, decision, bff)."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from src.modules.enrichment.application.dto.accounting import AccountingReportsDTO
from src.modules.enrichment.application.dto.cashflow import CashflowForecastDTO
from src.modules.enrichment.application.dto.counterparty import CounterpartyRiskDTO
from src.modules.enrichment.application.dto.credit_history import CreditHistoryDTO
from src.modules.enrichment.application.dto.registry import RegistryExtractDTO
from src.modules.enrichment.application.dto.tax import TaxProfileDTO
from src.modules.enrichment.domain.enums import Source

# Что источник кладёт в снимок.
SourceData = (
    RegistryExtractDTO
    | TaxProfileDTO
    | CreditHistoryDTO
    | CashflowForecastDTO
    | AccountingReportsDTO
    | CounterpartyRiskDTO
)


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
