"""Use case FetchEnrichment: опросить источники по заявке и сохранить снимок.

- источники опрашиваются параллельно, ошибка одного не мешает остальным (частичный
  результат — нормальный исход);
- БКИ запрашивается только при согласии (218-ФЗ), иначе `skipped`;
- идемпотентность по event_id команды: повтор возвращает тот же снимок и повторно
  публикует EnrichmentCompleted;
- causation_id ответа = event_id команды.
"""

from __future__ import annotations

import asyncio
import time
from typing import cast
from uuid import UUID, uuid4

from src.core.domain.clock import Clock
from src.core.messaging.contracts.enrichment import EnrichmentCompleted, FetchEnrichment
from src.core.messaging.outbox import OutboxWriter
from src.enrichment.application.ports import EnrichmentRepository, SourceError
from src.enrichment.application.sources import Sources
from src.enrichment.domain.snapshot import EnrichmentSnapshot, SourceData
from src.enrichment.domain.snapshot import SourceError as SnapshotError
from src.enrichment.facade import Source


class FetchEnrichmentUseCase:
    def __init__(self, repository: EnrichmentRepository, sources: Sources, clock: Clock) -> None:
        self._repository = repository
        self._sources = sources
        self._clock = clock

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
            if source == "bki" and command.bki_consent_at is None:
                snapshot.record_skipped(
                    "bki", SnapshotError("no_consent", "Нет согласия на запрос кредитной истории")
                )
                continue
            tasks.append(self._fetch(cast(Source, source), snapshot, command))
        if tasks:
            await asyncio.gather(*tasks)

        snapshot.completed_at = self._clock.now()
        await self._repository.add(snapshot)
        await self._publish(outbox, snapshot, command_event_id)

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
        raise SourceError("bad_response", f"Неизвестный источник {source!r}")

    async def _publish(
        self, outbox: OutboxWriter, snapshot: EnrichmentSnapshot, command_event_id: UUID
    ) -> None:
        await outbox.add(
            EnrichmentCompleted(
                application_id=snapshot.application_id,
                snapshot_id=snapshot.id,
                sources_ok=list(snapshot.sources_ok),
                sources_failed=list(snapshot.sources_failed),
            ),
            key=snapshot.application_id,
            correlation_id=snapshot.application_id,
            causation_id=command_event_id,
        )


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
