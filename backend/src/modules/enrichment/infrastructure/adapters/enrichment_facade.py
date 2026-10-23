"""`EnrichmentFacade` для соседей (scoring, decision, bff, clients): только зовёт use case'ы,
своей логики нет."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from src.modules.enrichment.application.dto.cashflow import CashflowForecastDTO
from src.modules.enrichment.application.dto.credit_history import CreditHistoryDTO, PersonDTO
from src.modules.enrichment.application.dto.registry import RegistryExtractDTO
from src.modules.enrichment.application.dto.snapshot import EnrichmentSnapshotDTO
from src.modules.enrichment.application.use_cases.get_snapshot import GetSnapshotUseCase
from src.modules.enrichment.application.use_cases.latest_cashflow import GetLatestCashflowUseCase
from src.modules.enrichment.application.use_cases.lookup_person_bureau import (
    LookupPersonBureauUseCase,
)
from src.modules.enrichment.application.use_cases.lookup_registry import LookupRegistryUseCase
from src.modules.enrichment.facade import EnrichmentFacade


class EnrichmentFacadeImpl(EnrichmentFacade):
    def __init__(
        self,
        get_snapshot: GetSnapshotUseCase,
        lookup_registry: LookupRegistryUseCase,
        lookup_person_bureau: LookupPersonBureauUseCase,
        latest_cashflow: GetLatestCashflowUseCase,
    ) -> None:
        self._get_snapshot = get_snapshot
        self._lookup_registry = lookup_registry
        self._lookup_person_bureau = lookup_person_bureau
        self._latest_cashflow = latest_cashflow

    async def get_snapshot(self, application_id: UUID) -> EnrichmentSnapshotDTO | None:
        return await self._get_snapshot.execute(application_id)

    async def latest_cashflow(self, organization_id: UUID) -> CashflowForecastDTO | None:
        return await self._latest_cashflow.execute(organization_id)

    async def lookup_registry(self, inn: str, *, fresh: bool = False) -> RegistryExtractDTO | None:
        return await self._lookup_registry.execute(inn, fresh=fresh)

    async def lookup_person_bureau(
        self, person: PersonDTO, consent_at: datetime
    ) -> CreditHistoryDTO | None:
        return await self._lookup_person_bureau.execute(person, consent_at)
