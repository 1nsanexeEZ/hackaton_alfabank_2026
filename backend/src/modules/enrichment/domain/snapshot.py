"""EnrichmentSnapshot — что внешние источники сказали о компании по одной заявке
на один момент. БКИ запрашивается только при согласии субъекта (218-ФЗ): без
согласия источник помечается `skipped`, а не запрашивается. БКИ руководителя — так же,
по его личному согласию; нет руководителя по реестру — тоже `skipped`.

Данные источников переносим в DTO из facade.py (они — чистые dataclass'ы), чтобы
не дублировать структуры; бизнес-логика снимка — здесь.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal
from uuid import UUID

from src.modules.enrichment.facade import (
    AccountingReportsDTO,
    CashflowForecastDTO,
    CounterpartyRiskDTO,
    CreditHistoryDTO,
    RegistryExtractDTO,
    Source,
    TaxProfileDTO,
)

SourceData = (
    RegistryExtractDTO
    | TaxProfileDTO
    | CreditHistoryDTO
    | CashflowForecastDTO
    | AccountingReportsDTO
    | CounterpartyRiskDTO
)
SourceStatus = Literal["ok", "failed", "skipped"]
# Прогноз по выписке строит сам модуль: это не внешний источник, в ok / failed он не считается.
INTERNAL_SOURCES: frozenset[Source] = frozenset({"statement"})


@dataclass(frozen=True, slots=True)
class SourceError:
    kind: str  # timeout | unavailable | not_found | bad_response | no_consent | no_head
    message: str


@dataclass(slots=True)
class SourceResult:
    source: Source
    status: SourceStatus
    fetched_at: datetime | None = None
    latency_ms: int | None = None
    attempts: int = 0
    data: SourceData | None = None
    error: SourceError | None = None


@dataclass(slots=True)
class EnrichmentSnapshot:
    id: UUID
    application_id: UUID
    organization_id: UUID
    inn: str
    requested_by_command: UUID
    requested_sources: tuple[Source, ...]
    started_at: datetime
    completed_at: datetime | None = None
    results: dict[Source, SourceResult] = field(default_factory=dict)

    def record_success(
        self,
        source: Source,
        data: SourceData,
        *,
        fetched_at: datetime,
        latency_ms: int | None = None,
        attempts: int = 1,
    ) -> None:
        self.results[source] = SourceResult(
            source=source,
            status="ok",
            fetched_at=fetched_at,
            latency_ms=latency_ms,
            attempts=attempts,
            data=data,
        )

    def record_failure(
        self,
        source: Source,
        error: SourceError,
        *,
        attempts: int = 1,
        latency_ms: int | None = None,
    ) -> None:
        self.results[source] = SourceResult(
            source=source,
            status="failed",
            latency_ms=latency_ms,
            attempts=attempts,
            error=error,
        )

    def record_skipped(self, source: Source, error: SourceError) -> None:
        self.results[source] = SourceResult(source=source, status="skipped", error=error)

    @property
    def is_complete(self) -> bool:
        return all(source in self.results for source in self.requested_sources)

    @property
    def sources_ok(self) -> list[Source]:
        # Только внешние источники; `statement` — внутренний, не считается.
        return self._external_with("ok")

    @property
    def sources_failed(self) -> list[Source]:
        return self._external_with("failed")

    @property
    def sources_skipped(self) -> list[Source]:
        return self._external_with("skipped")

    def _external_with(self, status: SourceStatus) -> list[Source]:
        return [
            s
            for s in self.requested_sources
            if s not in INTERNAL_SOURCES and s in self.results and self.results[s].status == status
        ]

    def _data(self, source: Source) -> SourceData | None:
        result = self.results.get(source)
        return result.data if result is not None and result.status == "ok" else None

    def registry(self) -> RegistryExtractDTO | None:
        data = self._data("egrul")
        return data if isinstance(data, RegistryExtractDTO) else None

    def tax(self) -> TaxProfileDTO | None:
        data = self._data("fns")
        return data if isinstance(data, TaxProfileDTO) else None

    def credit_history(self) -> CreditHistoryDTO | None:
        data = self._data("bki")
        return data if isinstance(data, CreditHistoryDTO) else None

    def head_credit_history(self) -> CreditHistoryDTO | None:
        data = self._data("bki_head")
        return data if isinstance(data, CreditHistoryDTO) else None

    def accounting(self) -> AccountingReportsDTO | None:
        data = self._data("gir_bo")
        return data if isinstance(data, AccountingReportsDTO) else None

    def counterparty(self) -> CounterpartyRiskDTO | None:
        data = self._data("kontur")
        return data if isinstance(data, CounterpartyRiskDTO) else None

    def record_cashflow(self, forecast: CashflowForecastDTO, *, fetched_at: datetime) -> None:
        self.results["statement"] = SourceResult(
            source="statement", status="ok", fetched_at=fetched_at, data=forecast
        )

    def record_cashflow_failed(self, error: SourceError) -> None:
        self.results["statement"] = SourceResult(source="statement", status="failed", error=error)

    def cashflow(self) -> CashflowForecastDTO | None:
        data = self._data("statement")
        return data if isinstance(data, CashflowForecastDTO) else None
