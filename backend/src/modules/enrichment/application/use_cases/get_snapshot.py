"""Последний снимок по заявке — для соседей (scoring, decision, bff)."""

from __future__ import annotations

from uuid import UUID

from src.modules.enrichment.application.dto.accounting import AccountingReportsDTO
from src.modules.enrichment.application.dto.aml import AmlCheckDTO
from src.modules.enrichment.application.dto.cashflow import CashflowForecastDTO
from src.modules.enrichment.application.dto.counterparty import CounterpartyRiskDTO
from src.modules.enrichment.application.dto.credit_history import CreditHistoryDTO
from src.modules.enrichment.application.dto.registry import RegistryExtractDTO
from src.modules.enrichment.application.dto.snapshot import EnrichmentSnapshotDTO, SourceErrorDTO
from src.modules.enrichment.application.dto.tax import TaxProfileDTO
from src.modules.enrichment.application.interfaces.repositories import EnrichmentRepository
from src.modules.enrichment.domain.enums import Source
from src.modules.enrichment.domain.snapshot import EnrichmentSnapshot


class GetSnapshotUseCase:
    def __init__(self, repository: EnrichmentRepository) -> None:
        self._repository = repository

    async def execute(self, application_id: UUID) -> EnrichmentSnapshotDTO | None:
        snapshot = await self._repository.latest_for_application(application_id)
        return to_dto(snapshot) if snapshot is not None else None


def to_dto(snapshot: EnrichmentSnapshot) -> EnrichmentSnapshotDTO:
    # sources_failed исключает внутренний `statement` (как и sources_ok) — симметрично
    # с доменным снимком; провал разбора выписки виден по cashflow=None, не как источник.
    return EnrichmentSnapshotDTO(
        id=snapshot.id,
        application_id=snapshot.application_id,
        organization_id=snapshot.organization_id,
        collected_at=snapshot.completed_at or snapshot.started_at,
        sources_ok=tuple(snapshot.sources_ok),
        sources_failed=_errors(snapshot, snapshot.sources_failed),
        egrul=snapshot.data_of("egrul", RegistryExtractDTO),
        fns=snapshot.data_of("fns", TaxProfileDTO),
        bki=snapshot.data_of("bki", CreditHistoryDTO),
        cashflow=snapshot.data_of("statement", CashflowForecastDTO),
        gir_bo=snapshot.data_of("gir_bo", AccountingReportsDTO),
        kontur=snapshot.data_of("kontur", CounterpartyRiskDTO),
        bki_head=snapshot.data_of("bki_head", CreditHistoryDTO),
        sources_skipped=_errors(snapshot, snapshot.sources_skipped),
        aml=snapshot.data_of("aml", AmlCheckDTO),
    )


def _errors(snapshot: EnrichmentSnapshot, sources: list[Source]) -> tuple[SourceErrorDTO, ...]:
    return tuple(
        SourceErrorDTO(source=source, code=error.kind, message=error.message)
        for source in sources
        if (error := snapshot.results[source].error) is not None
    )
