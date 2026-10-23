"""Последний прогноз движения денег по компании — для подбора продуктов (products).

Прогноз строится по выписке в заявке, поэтому он есть, только если компания когда-то подавала
выписку. Берём самый свежий снимок с прогнозом среди последних заявок компании; выписки не
было — None: разрыв неизвестен, а не «разрыва нет».
"""

from __future__ import annotations

from uuid import UUID

from src.modules.enrichment.application.dto.cashflow import CashflowForecastDTO
from src.modules.enrichment.application.interfaces.repositories import EnrichmentRepository

# Сколько последних снимков компании смотреть: выписка бывает не в каждой заявке.
RECENT_SNAPSHOTS = 10


class GetLatestCashflowUseCase:
    def __init__(self, repository: EnrichmentRepository) -> None:
        self._repository = repository

    async def execute(self, organization_id: UUID) -> CashflowForecastDTO | None:
        snapshots = await self._repository.recent_for_organization(
            organization_id, RECENT_SNAPSHOTS
        )
        for snapshot in snapshots:
            forecast = snapshot.data_of("statement", CashflowForecastDTO)
            if forecast is not None:
                return forecast
        return None
