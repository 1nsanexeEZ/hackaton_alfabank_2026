"""Use case StoreClientFeatures: по `EnrichmentCompleted` сохранить признаки клиента из снимка
обогащения в хранилище признаков. Повтор события снимок второй раз не пишет; снимка уже нет —
писать нечего (скоринг заявки тогда упадёт сам, решит процесс)."""

from __future__ import annotations

from src.core.messaging.contracts.enrichment import EnrichmentCompleted
from src.modules.applications.facade import ApplicationsFacade
from src.modules.enrichment.facade import EnrichmentFacade
from src.modules.scoring.application.client_features import ClientFeatureStore


class StoreClientFeaturesUseCase:
    def __init__(
        self,
        store: ClientFeatureStore,
        applications: ApplicationsFacade,
        enrichment: EnrichmentFacade,
    ) -> None:
        self._store = store
        self._applications = applications
        self._enrichment = enrichment

    async def execute(self, event: EnrichmentCompleted) -> None:
        snapshot = await self._enrichment.get_snapshot(event.application_id)
        if snapshot is None:
            return
        application = await self._applications.get_scoring_input(event.application_id)
        await self._store.record(application, snapshot)
