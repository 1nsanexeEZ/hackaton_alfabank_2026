"""Use case FetchEnrichment: опросить источники по заявке и сохранить снимок.

- источники опрашиваются параллельно, ошибка одного не мешает остальным (частичный
  результат — нормальный исход);
- БКИ запрашивается только при согласии (218-ФЗ), иначе `skipped`; БКИ руководителя — только
  при его личном согласии (`skipped`, `no_consent`) и если руководитель по реестру известен
  (`skipped`, `no_head`);
- `statement` в `sources` — прогноз по выпискам, он строится из `statement_document_ids`;
- `aml` — проверка по 115-ФЗ (бенефициары, перечни Росфинмониторинга, ПДЛ, ЗСК): после ЕГРЮЛ
  этого же снимка, на каждой команде заново — прошлые заявки клиента и их проверки не
  переиспользуются; не выполнилась — `aml` в `failed`;
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
    DeclaredOwnerRef,
    EnrichmentCompleted,
    EnrichmentFailed,
    FetchEnrichment,
    ThirdPartyRef,
)
from src.core.messaging.outbox import OutboxWriter
from src.modules.enrichment.application.dto.aml import (
    AmlSubjectDTO,
    DeclaredOwnerBasis,
    DeclaredOwnerDTO,
    SubjectRole,
)
from src.modules.enrichment.application.dto.cashflow import CashflowForecastDTO
from src.modules.enrichment.application.dto.credit_history import CreditHistoryDTO, PersonDTO
from src.modules.enrichment.application.dto.registry import RegistryExtractDTO
from src.modules.enrichment.application.dto.snapshot import SourceData
from src.modules.enrichment.application.interfaces.repositories import EnrichmentRepository
from src.modules.enrichment.application.interfaces.sources import Sources
from src.modules.enrichment.application.use_cases.build_cashflow import CashflowBuilder
from src.modules.enrichment.application.use_cases.check_aml import AmlCheck
from src.modules.enrichment.domain.consent_policy import skip_reason
from src.modules.enrichment.domain.enums import INTERNAL_SOURCES, Source
from src.modules.enrichment.domain.exceptions import SourceFetchError, StatementParseError
from src.modules.enrichment.domain.snapshot import EnrichmentSnapshot, SourceError


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
            if source in INTERNAL_SOURCES or source == "aml":
                continue
            skip = skip_reason(
                cast(Source, source),
                bki_consent=command.bki_consent_at is not None,
                head_known=command.head is not None,
                head_consent=command.head_bki_consent_at is not None,
            )
            if skip is not None:
                snapshot.record_skipped(cast(Source, source), skip)
                continue
            tasks.append(self._fetch(cast(Source, source), snapshot, command))
        if tasks:
            await asyncio.gather(*tasks)

        await self._add_cashflow(command, snapshot)
        await self._add_aml(command, snapshot)

        snapshot.completed_at = self._clock.now()
        await self._repository.add(snapshot)
        await self._publish(outbox, snapshot, command_event_id)

    async def _add_cashflow(self, command: FetchEnrichment, snapshot: EnrichmentSnapshot) -> None:
        if self._cashflow is None or not command.statement_document_ids:
            return
        try:
            forecast = await self._cashflow.build(
                command, snapshot.data_of("bki", CreditHistoryDTO)
            )
        except StatementParseError as exc:
            snapshot.record_cashflow_failed(SourceError("bad_response", str(exc)))
            return
        if forecast is not None:
            snapshot.record_cashflow(forecast, fetched_at=self._clock.now())

    async def _add_aml(self, command: FetchEnrichment, snapshot: EnrichmentSnapshot) -> None:
        if "aml" not in command.sources:
            return
        representatives = tuple(
            _fio(person.last_name, person.first_name, person.middle_name)
            for person in (command.representative,)
            if person is not None
        )
        started = time.perf_counter()
        try:
            check = await AmlCheck(self._sources).run(
                snapshot.data_of("egrul", RegistryExtractDTO),
                representatives=representatives,
                third_parties=tuple(_third_party(p) for p in command.third_parties),
                declared_owners=None
                if command.declared_owners is None
                else tuple(_declared_owner(o) for o in command.declared_owners),
            )
        except SourceFetchError as exc:
            snapshot.record_failure(
                "aml",
                SourceError(exc.kind, str(exc)),
                attempts=exc.attempts,
                latency_ms=_elapsed_ms(started),
            )
            return
        snapshot.record_success(
            "aml", check, fetched_at=self._clock.now(), latency_ms=_elapsed_ms(started)
        )

    async def _fetch(
        self, source: Source, snapshot: EnrichmentSnapshot, command: FetchEnrichment
    ) -> None:
        started = time.perf_counter()
        try:
            data = await self._call(source, command)
        except SourceFetchError as exc:
            snapshot.record_failure(
                source,
                SourceError(exc.kind, str(exc)),
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
            person = PersonDTO(head.last_name, head.first_name, head.middle_name, command.inn)
            return await self._sources.person_bureau.fetch(person, command.head_bki_consent_at)
        if source == "bank_stop_list":
            return await self._sources.bank_stop_list.fetch(command.inn)
        if source == "bank_turnover":
            return await self._sources.bank_turnover.fetch(command.inn)
        raise SourceFetchError("bad_response", f"Неизвестный источник {source!r}")

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
        cashflow = snapshot.data_of("statement", CashflowForecastDTO)
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


def _third_party(ref: ThirdPartyRef) -> AmlSubjectDTO:
    """Организация (и ИП) — по ИНН, человек — по ФИО."""
    role = cast(SubjectRole, ref.role)
    inn = ref.inn if ref.kind == "organization" else None
    return AmlSubjectDTO(role, ref.name, inn, _country(ref.country))


def _declared_owner(ref: DeclaredOwnerRef) -> DeclaredOwnerDTO:
    return DeclaredOwnerDTO(ref.name, cast(DeclaredOwnerBasis, ref.basis), _country(ref.country))


def _country(code: str | None) -> str | None:
    """Россия — как и не указанная страна: None."""
    return None if code is None or code.upper() == "RU" else code.upper()


def _fio(last_name: str, first_name: str, middle_name: str | None) -> str:
    return " ".join(part for part in (last_name, first_name, middle_name) if part)


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


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
