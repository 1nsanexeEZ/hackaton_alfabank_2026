"""Use case FetchEnrichment: опросить источники по заявке и сохранить снимок.

- источники опрашиваются параллельно, ошибка одного не мешает остальным (частичный
  результат — нормальный исход);
- БКИ запрашивается только при согласии (218-ФЗ), иначе `skipped`; БКИ руководителя — только
  при его личном согласии (`skipped`, `no_consent`) и если руководитель по реестру известен
  (`skipped`, `no_head`);
- `statement` в `sources` — прогноз по выпискам, он строится из `statement_document_ids`;
- не ответил ни один внешний источник (например, нет сети до моков) — считать не на чем:
  снимок сохраняется для аудита, но публикуется EnrichmentFailed, а не EnrichmentCompleted;
- идемпотентность по event_id команды: повтор возвращает тот же снимок и повторно
  публикует тот же ответ;
- causation_id ответа = event_id команды.
"""

from __future__ import annotations

import asyncio
import time
from typing import cast
from uuid import UUID, uuid4

from src.core.domain.clock import Clock
from src.core.messaging.contracts.enrichment import (
    EnrichmentCompleted,
    EnrichmentFailed,
    FetchEnrichment,
)
from src.core.messaging.outbox import OutboxWriter
from src.modules.enrichment.application.cashflow import CashflowBuilder
from src.modules.enrichment.application.ports import (
    EnrichmentRepository,
    PersonQuery,
    SourceError,
)
from src.modules.enrichment.application.sources import Sources
from src.modules.enrichment.domain.cashflow import StatementParseError
from src.modules.enrichment.domain.snapshot import INTERNAL_SOURCES, EnrichmentSnapshot, SourceData
from src.modules.enrichment.domain.snapshot import SourceError as SnapshotError
from src.modules.enrichment.facade import Source


class FetchEnrichmentUseCase:
    def __init__(
        self,
        repository: EnrichmentRepository,
        sources: Sources,
        clock: Clock,
        cashflow: CashflowBuilder | None = None,
    ) -> None:
        self._repository = repository
        self._sources = sources
        self._clock = clock
        self._cashflow = cashflow

    async def execute(
        self, command: FetchEnrichment, *, command_event_id: UUID, outbox: OutboxWriter
    ) -> None:
        existing = await self._repository.get_by_command(command_event_id)
        if existing is not None:
            await self._publish(outbox, existing, command_event_id)
            return

        snapshot = EnrichmentSnapshot(
            id=uuid4(),
            application_id=command.application_id,
            organization_id=command.organization_id,
            inn=command.inn,
            requested_by_command=command_event_id,
            requested_sources=tuple(cast(list[Source], command.sources)),
            started_at=self._clock.now(),
        )

        tasks = []
        for source in command.sources:
            if source in INTERNAL_SOURCES:
                continue
            skip = _skip_reason(cast(Source, source), command)
            if skip is not None:
                snapshot.record_skipped(cast(Source, source), skip)
                continue
            tasks.append(self._fetch(cast(Source, source), snapshot, command))
        if tasks:
            await asyncio.gather(*tasks)

        await self._add_cashflow(command, snapshot)

        snapshot.completed_at = self._clock.now()
        await self._repository.add(snapshot)
        await self._publish(outbox, snapshot, command_event_id)

    async def _add_cashflow(self, command: FetchEnrichment, snapshot: EnrichmentSnapshot) -> None:
        if self._cashflow is None or not command.statement_document_ids:
            return
        try:
            forecast = await self._cashflow.build(command, snapshot.credit_history())
        except StatementParseError as exc:
            snapshot.record_cashflow_failed(SnapshotError("bad_response", str(exc)))
            return
        if forecast is not None:
            snapshot.record_cashflow(forecast, fetched_at=self._clock.now())

    async def _fetch(
        self, source: Source, snapshot: EnrichmentSnapshot, command: FetchEnrichment
    ) -> None:
        started = time.perf_counter()
        try:
            data = await self._call(source, command)
        except SourceError as exc:
            snapshot.record_failure(
                source,
                SnapshotError(exc.kind, str(exc)),
                attempts=exc.attempts,
                latency_ms=_elapsed_ms(started),
            )
            return
        snapshot.record_success(
            source, data, fetched_at=self._clock.now(), latency_ms=_elapsed_ms(started)
        )

    async def _call(self, source: Source, command: FetchEnrichment) -> SourceData:
        if source == "egrul":
            return await self._sources.registry.fetch(command.inn)
        if source == "fns":
            return await self._sources.tax.fetch(command.inn)
        if source == "bki":
            assert command.bki_consent_at is not None
            return await self._sources.bureau.fetch(command.inn, command.bki_consent_at)
        if source == "gir_bo":
            return await self._sources.accounting.fetch(command.inn)
        if source == "kontur":
            return await self._sources.counterparty.fetch(command.inn)
        if source == "bki_head":
            head = command.head
            assert head is not None and command.head_bki_consent_at is not None
            person = PersonQuery(head.last_name, head.first_name, head.middle_name, command.inn)
            return await self._sources.person_bureau.fetch(person, command.head_bki_consent_at)
        raise SourceError("bad_response", f"Неизвестный источник {source!r}")

    async def _publish(
        self, outbox: OutboxWriter, snapshot: EnrichmentSnapshot, command_event_id: UUID
    ) -> None:
        if not snapshot.sources_ok:
            await outbox.add(
                EnrichmentFailed(
                    application_id=snapshot.application_id, reason=_failure_reason(snapshot)
                ),
                key=snapshot.application_id,
                correlation_id=snapshot.application_id,
                causation_id=command_event_id,
            )
            return
        cashflow = snapshot.cashflow()
        await outbox.add(
            EnrichmentCompleted(
                application_id=snapshot.application_id,
                snapshot_id=snapshot.id,
                sources_ok=list(snapshot.sources_ok),
                sources_failed=list(snapshot.sources_failed),
                cash_gap_detected=cashflow.gap_detected if cashflow is not None else None,
            ),
            key=snapshot.application_id,
            correlation_id=snapshot.application_id,
            causation_id=command_event_id,
        )


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _skip_reason(source: Source, command: FetchEnrichment) -> SnapshotError | None:
    """Источник не запрашиваем: нет согласия субъекта (218-ФЗ) или некого спрашивать."""
    if source == "bki" and command.bki_consent_at is None:
        return SnapshotError("no_consent", "Нет согласия на запрос кредитной истории")
    if source == "bki_head":
        if command.head is None:
            return SnapshotError("no_head", "Руководитель по реестру не найден среди участников")
        if command.head_bki_consent_at is None:
            return SnapshotError(
                "no_consent", "Нет согласия руководителя на запрос его кредитной истории"
            )
    return None


def _failure_reason(snapshot: EnrichmentSnapshot) -> str:
    """Например: `all_sources_failed: egrul=unavailable, fns=timeout, bki=no_consent`."""
    details = []
    for source in snapshot.requested_sources:
        if source in INTERNAL_SOURCES:
            continue
        result = snapshot.results.get(source)
        if result is None:
            kind = "not_requested"
        elif result.error is not None:
            kind = result.error.kind
        else:
            kind = result.status
        details.append(f"{source}={kind}")
    return "all_sources_failed: " + ", ".join(details)
