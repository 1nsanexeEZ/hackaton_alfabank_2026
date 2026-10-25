"""Версии PD-модели: реестр (черновик → активная → архив, откат), активная модель для команды
и предодобрения, примерка на прошлых результатах."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.domain.clock import FrozenClock
from src.core.exceptions.exceptions import InvalidStatusTransitionError, ValidationError
from src.core.facades import FacadeRegistry
from src.core.messaging.contracts.scoring import CalculateScore
from src.core.messaging.envelope import Envelope
from src.core.messaging.subscriber import HandlerContext
from src.modules.applications.facade import ApplicationsFacade
from src.modules.enrichment.facade import EnrichmentFacade
from src.modules.scoring import module as scoring_module
from src.modules.scoring.application.model_versions import ActiveModelProvider, ModelVersions
from src.modules.scoring.application.serialization import dump_input, input_hash
from src.modules.scoring.domain.model import ScoringResult
from src.modules.scoring.facade import CompanyProfileDTO
from src.modules.scoring.infrastructure.config_loader import (
    PdModelDocuments,
    load_pd_model,
    load_scorecard,
)
from src.modules.scoring.infrastructure.facade_impl import ScoringFacadeImpl
from src.modules.scoring.infrastructure.models import (
    ScoringModelVersionRecord,
    ScoringResultRecord,
)
from src.modules.scoring.infrastructure.repository import (
    SqlAlchemyModelVersionRepository,
    SqlAlchemyScoringRepository,
)
from tests.fakes.enrichment_facade import FakeEnrichmentFacade
from tests.fakes.messaging import FakeOutboxWriter
from tests.scoring.scenarios import SCENARIOS
from tests.scoring.test_calculate_score import _romashka_bki, _setup, _snapshot

Sessions = async_sessionmaker[AsyncSession]

_NOW = datetime(2026, 11, 5, 10, 0, tzinfo=UTC)
_ADMIN = uuid4()
_BUILTIN = "pd_model_v2"
_MODEL = load_pd_model()


def _versions(session: AsyncSession) -> ModelVersions:
    return ModelVersions(
        SqlAlchemyModelVersionRepository(session), PdModelDocuments(), FrozenClock(_NOW)
    )


def _richer(body: dict[str, Any], shift: int = 100) -> dict[str, Any]:
    """Та же модель, но каждой скоркарте база на `shift` баллов выше."""
    for card in body["scorecards"].values():
        card["base"] += shift
    return body


async def _draft(sessions: Sessions, based_on: str = _BUILTIN, shift: int = 0) -> str:
    async with sessions() as session:
        versions = _versions(session)
        draft = await versions.create_draft(based_on, "проба", _ADMIN)
        if shift:
            await versions.update_draft(draft.version, _richer(draft.body, shift), None)
        await session.commit()
    return draft.version


async def _activate(sessions: Sessions, version: str) -> None:
    async with sessions() as session:
        await _versions(session).activate(version, _ADMIN)
        await session.commit()


async def _statuses(sessions: Sessions) -> dict[str, str]:
    async with sessions() as session:
        return {v.version: v.status for v in await _versions(session).list_all()}


async def test_builtin_is_in_force_without_versions(session_factory: Sessions) -> None:
    async with session_factory() as session:
        [builtin] = await _versions(session).list_all()
        model = await ActiveModelProvider(PdModelDocuments()).active(
            SqlAlchemyModelVersionRepository(session)
        )
    assert (builtin.version, builtin.status, builtin.builtin) == (_BUILTIN, "active", True)
    assert builtin.body["version"] == _BUILTIN
    assert model.version == _BUILTIN


async def test_draft_is_a_copy_under_the_next_number(session_factory: Sessions) -> None:
    first = await _draft(session_factory)
    second = await _draft(session_factory)
    third = await _draft(session_factory, based_on=first)

    assert (first, second, third) == ("pd_model_v2.1", "pd_model_v2.2", "pd_model_v2.3")
    async with session_factory() as session:
        draft = await _versions(session).get(third)
        builtin = await _versions(session).get(_BUILTIN)
    assert (draft.status, draft.based_on, draft.created_by) == ("draft", first, _ADMIN)
    # Код версии внутри документа — всегда код самой версии: он пишется в результаты.
    assert draft.body["version"] == third
    assert {**draft.body, "version": _BUILTIN} == builtin.body


async def test_activation_archives_the_previous_and_rolls_back(session_factory: Sessions) -> None:
    first = await _draft(session_factory, shift=100)
    await _activate(session_factory, first)
    assert await _statuses(session_factory) == {_BUILTIN: "archived", first: "active"}

    second = await _draft(session_factory, shift=200)
    await _activate(session_factory, second)
    assert await _statuses(session_factory) == {
        _BUILTIN: "archived",
        first: "archived",
        second: "active",
    }

    # Откат на архивную версию.
    await _activate(session_factory, first)
    assert await _statuses(session_factory) == {
        _BUILTIN: "archived",
        first: "active",
        second: "archived",
    }
    async with session_factory() as session:
        rolled_back = await _versions(session).get(first)
    assert rolled_back.activated_by == _ADMIN and rolled_back.activated_at is not None

    # Вернуть встроенную: активная версия из БД уходит в архив.
    await _activate(session_factory, _BUILTIN)
    assert await _statuses(session_factory) == {
        _BUILTIN: "active",
        first: "archived",
        second: "archived",
    }
    with pytest.raises(InvalidStatusTransitionError):
        await _activate(session_factory, _BUILTIN)


async def test_only_a_draft_is_changed_or_deleted(session_factory: Sessions) -> None:
    active = await _draft(session_factory)
    await _activate(session_factory, active)
    draft = await _draft(session_factory)

    async with session_factory() as session:
        versions = _versions(session)
        body = (await versions.get(active)).body
        for version in (active, _BUILTIN):
            with pytest.raises(InvalidStatusTransitionError):
                await versions.update_draft(version, body, None)
            with pytest.raises(InvalidStatusTransitionError):
                await versions.delete_draft(version)
        with pytest.raises(InvalidStatusTransitionError):
            await versions.activate(active, _ADMIN)  # уже активна
        await versions.delete_draft(draft)
        await session.commit()

    assert set(await _statuses(session_factory)) == {_BUILTIN, active}


async def test_broken_document_lists_every_problem(session_factory: Sessions) -> None:
    draft = await _draft(session_factory)
    async with session_factory() as session:
        versions = _versions(session)
        body = (await versions.get(draft)).body
        features = body["scorecards"]["legal_entity"]["features"]
        features["debt_load"]["bins"].pop(1)  # дырка между бинами
        body["grades"].pop("I")
        with pytest.raises(ValidationError) as error:
            await versions.update_draft(draft, body, None)

    assert error.value.status_code == 422
    paths = {e["path"] for e in error.value.details["errors"]}  # type: ignore[index]
    assert paths == {"grades", "scorecards.legal_entity.features.debt_load.bins"}


async def test_one_active_version_is_kept_by_the_database(session_factory: Sessions) -> None:
    def record(version: str) -> ScoringModelVersionRecord:
        return ScoringModelVersionRecord(
            version=version,
            status="active",
            body={},
            created_by=_ADMIN,
            created_at=_NOW,
            updated_at=_NOW,
        )

    async with session_factory() as session:
        session.add_all([record("pd_model_v2.1"), record("pd_model_v2.2")])
        with pytest.raises(IntegrityError):
            await session.flush()


async def test_provider_takes_the_active_version_and_keeps_it(session_factory: Sessions) -> None:
    provider = ActiveModelProvider(PdModelDocuments())
    version = await _draft(session_factory, shift=100)
    await _activate(session_factory, version)

    async with session_factory() as session:
        repository = SqlAlchemyModelVersionRepository(session)
        model = await provider.active(repository)
        again = await provider.active(repository)

    assert model.version == version
    assert again is model  # собрана один раз на процесс
    scenario = SCENARIOS["romashka_s1"]
    assert model.calculate(scenario).score == _MODEL.calculate(scenario).score + 100


async def test_estimate_scores_by_the_active_version(session_factory: Sessions) -> None:
    profile = CompanyProfileDTO(
        legal_form="LLC",
        business_age_months=72,
        okved_main="56.10",
        annual_revenue=None,
        previous_annual_revenue=None,
        verification_status="verified",
        registry_status="active",
    )
    provider = ActiveModelProvider(PdModelDocuments())
    async with session_factory() as session:
        before = await ScoringFacadeImpl(session, provider).estimate(profile)
    await _activate(session_factory, await _draft(session_factory, shift=100))
    async with session_factory() as session:
        after = await ScoringFacadeImpl(session, provider).estimate(profile)

    assert after.score == before.score + 100


async def test_command_scores_by_the_active_version(
    session_factory: Sessions, monkeypatch: pytest.MonkeyPatch
) -> None:
    version = await _draft(session_factory, shift=100)
    await _activate(session_factory, version)
    monkeypatch.setattr(scoring_module, "_models", ActiveModelProvider(PdModelDocuments()))
    scoring_input, applications = _setup()
    enrichment = FakeEnrichmentFacade()
    enrichment.add_snapshot(
        _snapshot(scoring_input.application_id, scoring_input.organization_id, bki=_romashka_bki())
    )
    facades = FacadeRegistry()
    facades.register(ApplicationsFacade, lambda _: applications)  # type: ignore[type-abstract]
    facades.register(EnrichmentFacade, lambda _: enrichment)  # type: ignore[type-abstract]

    async with session_factory() as session:
        context = HandlerContext(
            envelope=Envelope(
                event_id=uuid4(),
                type=CalculateScore.TYPE,
                schema_version=1,
                occurred_at=_NOW,
                producer="process",
                correlation_id=scoring_input.application_id,
                payload={},
            ),
            session=session,
            outbox=FakeOutboxWriter(),  # type: ignore[arg-type]
            facades=facades,
            clock=FrozenClock(_NOW),
        )
        await scoring_module._on_calculate_score(
            context, CalculateScore(application_id=scoring_input.application_id)
        )
        stored = (await session.scalars(select(ScoringResultRecord))).one()

    assert stored.model_version == version


# --- примерка -------------------------------------------------------------------------------


async def _score(
    sessions: Sessions, scenario: str, *, at: datetime, application_id: UUID | None = None
) -> UUID:
    """Результат встроенной PD-модели на сценарии, как его пишет команда."""
    scoring_input = SCENARIOS[scenario]
    output = _MODEL.calculate(scoring_input)
    stored = dump_input(scoring_input)
    result = ScoringResult(
        id=uuid4(),
        application_id=application_id or uuid4(),
        requested_by_command=uuid4(),
        model_version=_MODEL.version,
        score=output.score,
        grade=output.grade,
        factors=output.factors,
        flags=output.flags,
        data_completeness=output.data_completeness,
        computed_at=at,
        input_hash=input_hash(stored),
        segment=output.segment,
        scorecard=output.scorecard,
        pd_12m=output.pd_12m,
        reason_codes=output.reason_codes,
    )
    async with sessions() as session:
        await SqlAlchemyScoringRepository(session).add(result, input_snapshot=stored)
        await session.commit()
    return result.application_id


async def test_preview_scores_the_latest_applications_again(session_factory: Sessions) -> None:
    romashka = await _score(session_factory, "romashka_s1", at=_NOW - timedelta(hours=3))
    # Повторный расчёт той же заявки: в примерку идёт только последний.
    await _score(
        session_factory, "romashka_s1", at=_NOW - timedelta(hours=2), application_id=romashka
    )
    vector = await _score(session_factory, "vector_s3", at=_NOW - timedelta(hours=1))
    # Результат scorecard_v1 (без PD) в примерку не идёт.
    async with session_factory() as session:
        scorecard = SCENARIOS["ivanov_s2"]
        output = load_scorecard().calculate(scorecard)
        await SqlAlchemyScoringRepository(session).add(
            ScoringResult(
                id=uuid4(),
                application_id=uuid4(),
                requested_by_command=uuid4(),
                model_version="scorecard_v1",
                score=output.score,
                grade=output.grade,
                factors=output.factors,
                flags=output.flags,
                data_completeness=output.data_completeness,
                computed_at=_NOW,
            ),
            input_snapshot=dump_input(scorecard),
        )
        await session.commit()
    version = await _draft(session_factory, shift=-300)

    async with session_factory() as session:
        preview = await _versions(session).preview(
            version, 50, SqlAlchemyScoringRepository(session)
        )
        results = (await session.scalars(select(ScoringResultRecord))).all()

    assert len(results) == 4  # примерка ничего не пишет
    assert [item.application_id for item in preview.items] == [vector, romashka]
    for item in preview.items:
        assert item.before.model_version == _BUILTIN
        assert item.after.model_version == version
        assert item.after.score == item.before.score - 300
        assert item.before.pd_12m is not None and item.after.pd_12m is not None
        assert item.after.pd_12m > item.before.pd_12m
    assert preview.worse == 2 and preview.same == preview.better == preview.skipped == 0
    assert sum(shift.count for shift in preview.transitions) == 2

    async with session_factory() as session:
        same = await _versions(session).preview(_BUILTIN, 1, SqlAlchemyScoringRepository(session))
    assert len(same.items) == 1 and same.same == 1
    assert same.items[0].before.score == same.items[0].after.score
