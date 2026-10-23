"""EnrichmentSnapshot — что внешние источники сказали о компании по одной заявке
на один момент. БКИ запрашивается только при согласии субъекта (218-ФЗ): без
согласия источник помечается `skipped`, а не запрашивается. БКИ руководителя — так же,
по его личному согласию; нет руководителя по реестру — тоже `skipped`.

Ответ источника для снимка — непрозрачные данные: снимок следит за статусами, а форму данных
задают DTO слоя application. Типизированно их достают через `data_of`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from src.modules.enrichment.domain.enums import INTERNAL_SOURCES, Source, SourceStatus


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
    data: object | None = None
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
        data: object,
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

    def data_of[T](self, source: Source, kind: type[T]) -> T | None:
        """Данные источника, если он ответил и данные нужного вида."""
        result = self.results.get(source)
        if result is None or result.status != "ok":
            return None
        return result.data if isinstance(result.data, kind) else None

    def record_cashflow(self, forecast: object, *, fetched_at: datetime) -> None:
        self.results["statement"] = SourceResult(
            source="statement", status="ok", fetched_at=fetched_at, data=forecast
        )

    def record_cashflow_failed(self, error: SourceError) -> None:
        self.results["statement"] = SourceResult(source="statement", status="failed", error=error)
