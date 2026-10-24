"""Хранилище признаков клиента: запись по снимку обогащения и выбор на дату заявки.

- `record` — признаки клиента из снимка обогащения заявки; повтор по тому же снимку не пишет
  второй раз (идемпотентность по `enrichment_snapshot_id`);
- `scoring_input` — вход скоринга: признаки заявки из заявки, признаки клиента — самый свежий
  снимок компании не старше `max_age_days` на дату заявки. Нет такого или обогащение этой заявки
  новее (дозагрузили выписку) — признаки считаются из снимка обогащения и сохраняются.

Признаки клиента считаются на дату заявки, по которой собирали снимок (обороты в банке — в
месяцах до неё), `as_of` снимка — дата сбора данных.
"""

from __future__ import annotations

from uuid import uuid4

from src.modules.applications.facade import ScoringInputDTO
from src.modules.enrichment.facade import EnrichmentSnapshotDTO
from src.modules.scoring.application.input_builder import build_scoring_input
from src.modules.scoring.application.ports import FeatureSnapshotRepository
from src.modules.scoring.domain.client_features import (
    FeatureSnapshot,
    FeatureStorePolicy,
    client_features,
    with_client_features,
)
from src.modules.scoring.domain.model import ScoringInput


class ClientFeatureStore:
    def __init__(self, repository: FeatureSnapshotRepository, policy: FeatureStorePolicy) -> None:
        self._repository = repository
        self._policy = policy

    async def record(
        self, application: ScoringInputDTO, snapshot: EnrichmentSnapshotDTO
    ) -> FeatureSnapshot:
        existing = await self._repository.get_by_enrichment_snapshot(snapshot.id)
        if existing is not None:
            return existing
        stored = FeatureSnapshot(
            id=uuid4(),
            organization_id=snapshot.organization_id,
            as_of=snapshot.collected_at.date(),
            collected_at=snapshot.collected_at,
            enrichment_snapshot_id=snapshot.id,
            features=client_features(build_scoring_input(application, snapshot)),
            sources=tuple(snapshot.sources_ok),
        )
        await self._repository.add(stored)
        return stored

    async def scoring_input(
        self, application: ScoringInputDTO, snapshot: EnrichmentSnapshotDTO
    ) -> tuple[ScoringInput, FeatureSnapshot]:
        as_of = application.submitted_at.date()
        stored = await self._repository.latest(
            snapshot.organization_id, since=self._policy.oldest_as_of(as_of)
        )
        if stored is None or not self._policy.usable(stored, snapshot.collected_at):
            stored = await self.record(application, snapshot)
        own = build_scoring_input(application, snapshot)
        return with_client_features(own.request, own.collateral, as_of, stored.features), stored
