"""Хранилище признаков клиента: запись по EnrichmentCompleted, выбор на дату заявки, репозиторий."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.domain.clock import FrozenClock
from src.core.messaging.contracts.enrichment import EnrichmentCompleted
from src.core.messaging.contracts.scoring import CalculateScore, ScoreCalculated
from src.modules.enrichment.facade import EnrichmentSnapshotDTO
from src.modules.scoring.application.calculate_score import CalculateScoreUseCase
from src.modules.scoring.application.client_features import ClientFeatureStore
from src.modules.scoring.application.input_builder import build_scoring_input
from src.modules.scoring.application.serialization import dump_input, input_hash, load_input
from src.modules.scoring.application.store_client_features import StoreClientFeaturesUseCase
from src.modules.scoring.domain.client_features import (
    ClientFeatures,
    FeatureSnapshot,
    client_features,
)
from src.modules.scoring.infrastructure.config_loader import load_feature_store
from src.modules.scoring.infrastructure.repository import SqlAlchemyFeatureSnapshotRepository
from tests.fakes.enrichment_facade import FakeEnrichmentFacade
from tests.fakes.messaging import FakeOutboxWriter
from tests.scoring.test_calculate_score import (
    _CARD,
    _NOW,
    InMemoryScoringRepo,
    _romashka_bki,
    _setup,
    _snapshot,
)

_POLICY = load_feature_store()


class InMemoryFeatureSnapshots:
    def __init__(self) -> None:
        self.items: list[FeatureSnapshot] = []

    async def add(self, snapshot: FeatureSnapshot) -> None:
        self.items.append(snapshot)

    async def get_by_enrichment_snapshot(self, snapshot_id: UUID) -> FeatureSnapshot | None:
        return next((s for s in self.items if s.enrichment_snapshot_id == snapshot_id), None)

    async def latest(self, organization_id: UUID, *, since: date) -> FeatureSnapshot | None:
        found = [s for s in self.items if s.organization_id == organization_id and s.as_of >= since]
        return max(found, key=lambda s: s.collected_at, default=None)


def _world():
    scoring_input, apps = _setup()
    enrichment = FakeEnrichmentFacade()
    snapshot = _snapshot(
        scoring_input.application_id, scoring_input.organization_id, bki=_romashka_bki()
    )
    enrichment.add_snapshot(snapshot)
    store = InMemoryFeatureSnapshots()
    repo = InMemoryScoringRepo()
    use_case = CalculateScoreUseCase(
        repo,
        _CARD,
        apps,
        enrichment,
        FrozenClock(_NOW),
        features=ClientFeatureStore(store, _POLICY),
    )
    return use_case, repo, store, scoring_input, apps, enrichment, snapshot


def _stored(
    snapshot: EnrichmentSnapshotDTO, features_from: ClientFeatures, *, days_ago: int
) -> FeatureSnapshot:
    """Снимок признаков клиента, собранный `days_ago` дней назад по чужому снимку обогащения."""
    collected_at = snapshot.collected_at - timedelta(days=days_ago)
    return FeatureSnapshot(
        id=uuid4(),
        organization_id=snapshot.organization_id,
        as_of=collected_at.date(),
        collected_at=collected_at,
        enrichment_snapshot_id=uuid4(),
        features=features_from,
        sources=("egrul", "fns", "bki"),
    )


async def _score(use_case: CalculateScoreUseCase, application_id: UUID) -> FakeOutboxWriter:
    outbox = FakeOutboxWriter()
    await use_case.execute(
        CalculateScore(application_id=application_id), command_event_id=uuid4(), outbox=outbox
    )
    return outbox


async def test_without_a_stored_snapshot_features_are_computed_and_saved() -> None:
    use_case, repo, store, scoring_input, apps, _, snapshot = _world()

    outbox = await _score(use_case, scoring_input.application_id)

    assert len(store.items) == 1
    saved = store.items[0]
    assert saved.enrichment_snapshot_id == snapshot.id
    assert saved.as_of == snapshot.collected_at.date()
    assert saved.organization_id == scoring_input.organization_id
    result, stored = repo.added[0]
    assert stored["feature_snapshot_id"] == str(saved.id)
    # Тот же вход, что без хранилища: результат S-1 не меняется.
    own = build_scoring_input(apps.scoring_inputs[scoring_input.application_id], snapshot)
    assert load_input(stored) == own
    assert (result.score, result.grade) == (790, "A")
    assert outbox.of_type(ScoreCalculated)[0].score == 790


async def test_a_fresh_stored_snapshot_is_used() -> None:
    """Свежий снимок признаков (не старее обогащения заявки) берётся из хранилища."""
    use_case, repo, store, scoring_input, apps, _, snapshot = _world()
    own = build_scoring_input(apps.scoring_inputs[scoring_input.application_id], snapshot)
    overdue = client_features(replace(own, bureau=replace(own.bureau, max_overdue_days_12m=45)))
    fresh = replace(_stored(snapshot, overdue, days_ago=0), collected_at=snapshot.collected_at)
    store.items.append(fresh)

    await _score(use_case, scoring_input.application_id)

    assert len(store.items) == 1  # ничего не дописали
    result, stored = repo.added[0]
    assert stored["feature_snapshot_id"] == str(fresh.id)
    assert stored["bureau"]["max_overdue_days_12m"] == 45
    assert stored["request"]["amount"] == "3000000"  # признаки заявки — из заявки
    assert result.score < 790


async def test_a_stale_stored_snapshot_is_not_used() -> None:
    """Старше `max_age_days` на дату заявки — считаем из снимка обогащения и сохраняем новый."""
    use_case, repo, store, scoring_input, apps, _, snapshot = _world()
    own = build_scoring_input(apps.scoring_inputs[scoring_input.application_id], snapshot)
    stale = _stored(snapshot, client_features(own), days_ago=_POLICY.max_age_days + 5)
    store.items.append(stale)

    await _score(use_case, scoring_input.application_id)

    assert len(store.items) == 2
    _, stored = repo.added[0]
    assert stored["feature_snapshot_id"] == str(store.items[1].id)


async def test_newer_enrichment_of_the_application_wins_over_the_store() -> None:
    """Дозагрузили выписку: обогащение заявки новее снимка в хранилище — берём его."""
    use_case, repo, store, scoring_input, apps, _, snapshot = _world()
    own = build_scoring_input(apps.scoring_inputs[scoring_input.application_id], snapshot)
    older = _stored(snapshot, client_features(own), days_ago=2)
    store.items.append(older)

    await _score(use_case, scoring_input.application_id)

    _, stored = repo.added[0]
    assert stored["feature_snapshot_id"] == str(store.items[1].id)
    assert store.items[1].enrichment_snapshot_id == snapshot.id


async def test_the_feature_snapshot_reference_does_not_break_replay() -> None:
    use_case, repo, _, scoring_input, _, _, _ = _world()

    await _score(use_case, scoring_input.application_id)

    result, stored = repo.added[0]
    assert input_hash(stored) == result.input_hash
    assert _CARD.calculate(load_input(stored)).score == result.score
    # Без ссылки на хранилище снимок входа — прежний: старые снимки хешируются, как раньше.
    assert set(stored) - set(dump_input(load_input(stored))) == {"feature_snapshot_id"}


async def test_enrichment_completed_stores_client_features_once() -> None:
    scoring_input, apps = _setup()
    enrichment = FakeEnrichmentFacade()
    snapshot = _snapshot(
        scoring_input.application_id, scoring_input.organization_id, bki=_romashka_bki()
    )
    enrichment.add_snapshot(snapshot)
    store = InMemoryFeatureSnapshots()
    use_case = StoreClientFeaturesUseCase(ClientFeatureStore(store, _POLICY), apps, enrichment)
    event = EnrichmentCompleted(
        application_id=scoring_input.application_id, snapshot_id=snapshot.id
    )

    await use_case.execute(event)
    await use_case.execute(event)

    assert len(store.items) == 1
    assert store.items[0].sources == ("egrul", "fns")
    own = build_scoring_input(scoring_input, snapshot)
    assert store.items[0].features == client_features(own)


async def test_enrichment_completed_without_a_snapshot_stores_nothing() -> None:
    scoring_input, apps = _setup()
    store = InMemoryFeatureSnapshots()
    use_case = StoreClientFeaturesUseCase(
        ClientFeatureStore(store, _POLICY), apps, FakeEnrichmentFacade()
    )

    await use_case.execute(
        EnrichmentCompleted(application_id=scoring_input.application_id, snapshot_id=uuid4())
    )

    assert store.items == []


async def test_repository_round_trip_and_latest(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    scoring_input, _ = _setup()
    snapshot = _snapshot(
        scoring_input.application_id, scoring_input.organization_id, bki=_romashka_bki()
    )
    features = client_features(build_scoring_input(scoring_input, snapshot))
    older = _stored(snapshot, features, days_ago=3)
    newer = replace(_stored(snapshot, features, days_ago=1), enrichment_snapshot_id=snapshot.id)
    async with session_factory() as session:
        repository = SqlAlchemyFeatureSnapshotRepository(session)
        await repository.add(older)
        await repository.add(newer)
        await session.commit()

    async with session_factory() as session:
        repository = SqlAlchemyFeatureSnapshotRepository(session)
        latest = await repository.latest(snapshot.organization_id, since=older.as_of)
        assert latest == newer
        assert await repository.get_by_enrichment_snapshot(snapshot.id) == newer
        assert await repository.latest(uuid4(), since=older.as_of) is None
        assert (
            await repository.latest(snapshot.organization_id, since=newer.as_of + timedelta(1))
            is None
        )
