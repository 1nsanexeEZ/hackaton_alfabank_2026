from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.domain.clock import FrozenClock
from src.modules.scoring.application.model_versions import FixedModel
from src.modules.scoring.application.serialization import dump_input, input_hash, load_input
from src.modules.scoring.domain.model import ScoringInput, ScoringResult
from src.modules.scoring.domain.scorecard import ScorecardOutput
from src.modules.scoring.facade import CompanyProfileDTO
from src.modules.scoring.infrastructure.config_loader import load_pd_model, load_scorecard
from src.modules.scoring.infrastructure.facade_impl import ScoringFacadeImpl
from src.modules.scoring.infrastructure.ml_loader import load_ml_model
from src.modules.scoring.infrastructure.models import ScoringResultRecord
from src.modules.scoring.infrastructure.repository import SqlAlchemyScoringRepository
from tests.scoring.scenarios import SCENARIOS

_NOW = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)
_CARD = load_scorecard()
_MODEL = load_pd_model()
_ML = load_ml_model()


async def test_pd_model_result_roundtrips(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    scoring_input = SCENARIOS["vector_s3"]
    output = _MODEL.calculate(scoring_input)
    stored = dump_input(scoring_input)
    result = ScoringResult(
        id=uuid4(),
        application_id=uuid4(),
        requested_by_command=uuid4(),
        model_version=_MODEL.version,
        score=output.score,
        grade=output.grade,
        factors=output.factors,
        flags=output.flags,
        data_completeness=output.data_completeness,
        computed_at=_NOW,
        input_hash=input_hash(stored),
        segment=output.segment,
        scorecard=output.scorecard,
        pd_12m=output.pd_12m,
        reason_codes=output.reason_codes,
        ml=_ML.predict(scoring_input),
        quality="degraded",
        quality_reasons=("source_failed:fns",),
    )
    async with session_factory() as session:
        await SqlAlchemyScoringRepository(session).add(result, input_snapshot=stored)
        await session.commit()

    async with session_factory() as session:
        dto = await ScoringFacadeImpl(session, FixedModel(_MODEL)).get_result(result.application_id)
        stored_result = await SqlAlchemyScoringRepository(session).latest_for_application(
            result.application_id
        )

    assert dto is not None
    assert (dto.quality, dto.quality_reasons) == ("degraded", ("source_failed:fns",))
    assert stored_result is not None and stored_result.quality == "degraded"
    assert (dto.segment, dto.scorecard, dto.grade) == ("legal_entity", "legal_entity_v1", "F")
    assert dto.pd_12m == Decimal("0.0421")
    assert dto.reason_codes == ("amount_to_revenue", "industry_risk", "verification")
    # ML-модель рядом с PD-моделью — на той же шкале, с факторами и кодами причин.
    assert stored_result is not None and stored_result.ml == result.ml
    assert dto.ml is not None and result.ml is not None
    assert (dto.ml.model_version, dto.ml.grade, dto.ml.pd_12m) == (
        "ml_logreg_v1",
        "F",
        Decimal("0.0433"),
    )
    assert dto.ml.reason_codes == ("industry_risk", "debt_service_ratio", "bureau_inquiries")
    assert [f.code for f in dto.ml.factors] == [f.code for f in result.ml.factors]


async def test_scorecard_v1_result_has_no_pd(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    result, stored = _result()
    async with session_factory() as session:
        await SqlAlchemyScoringRepository(session).add(result, input_snapshot=stored)
        await session.commit()

    async with session_factory() as session:
        dto = await ScoringFacadeImpl(session, FixedModel(_CARD)).get_result(result.application_id)

    assert dto is not None
    assert (dto.segment, dto.pd_12m, dto.reason_codes, dto.ml) == (None, None, (), None)
    assert (dto.quality, dto.quality_reasons) == (None, ())


async def test_reason_for_no_ml_estimate_is_stored(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    result, stored = _result()
    result = replace(result, ml=None, ml_not_applicable="no_revenue")
    async with session_factory() as session:
        await SqlAlchemyScoringRepository(session).add(result, input_snapshot=stored)
        await session.commit()

    async with session_factory() as session:
        dto = await ScoringFacadeImpl(session, FixedModel(_CARD)).get_result(result.application_id)
        stored_result = await SqlAlchemyScoringRepository(session).latest_for_application(
            result.application_id
        )

    assert stored_result is not None and stored_result.ml_not_applicable == "no_revenue"
    assert dto is not None and dto.ml is None and dto.ml_not_applicable == "no_revenue"


async def test_estimate_of_the_pd_model_carries_segment_and_pd() -> None:
    profile = CompanyProfileDTO(
        legal_form="LLC",
        business_age_months=3,
        okved_main="56.10",
        annual_revenue=None,
        previous_annual_revenue=None,
        verification_status="verified",
        registry_status="active",
    )
    facade = ScoringFacadeImpl(None, FixedModel(_MODEL))  # type: ignore[arg-type]
    estimate = await facade.estimate(profile)
    assert estimate.segment == "new_client"
    assert estimate.pd_12m is not None and estimate.grade in set("ABCDEFGHIJ")


async def test_estimate_is_dated_by_the_application_clock() -> None:
    """Оценка для предодобрения берёт дату из часов приложения, а не из системной даты."""
    seen: list[ScoringInput] = []

    class Spy:
        version = _MODEL.version

        def calculate(self, inp: ScoringInput) -> ScorecardOutput:
            seen.append(inp)
            return _MODEL.calculate(inp)

    profile = CompanyProfileDTO(
        legal_form="LLC",
        business_age_months=40,
        okved_main="56.10",
        annual_revenue=Decimal("48000000"),
        previous_annual_revenue=None,
        verification_status="verified",
        registry_status="active",
    )
    clock = FrozenClock(datetime(2025, 3, 14, 23, 30, tzinfo=UTC))
    facade = ScoringFacadeImpl(None, FixedModel(Spy()), clock=clock)  # type: ignore[arg-type]
    await facade.estimate(profile)
    assert seen[0].as_of.isoformat() == "2025-03-14"


def _result() -> tuple[ScoringResult, dict]:
    scoring_input = SCENARIOS["ivanov_s2"]
    output = _CARD.calculate(scoring_input)
    stored = dump_input(scoring_input)
    result = ScoringResult(
        id=uuid4(),
        application_id=uuid4(),
        requested_by_command=uuid4(),
        model_version=_CARD.version,
        score=output.score,
        grade=output.grade,
        factors=output.factors,
        flags=output.flags,
        data_completeness=output.data_completeness,
        computed_at=_NOW,
        input_hash=input_hash(stored),
        bank_notes=output.bank_notes,
    )
    return result, stored


async def test_result_roundtrips_through_facade(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    result, stored = _result()
    async with session_factory() as session:
        await SqlAlchemyScoringRepository(session).add(result, input_snapshot=stored)
        await session.commit()

    async with session_factory() as session:
        dto = await ScoringFacadeImpl(session, FixedModel(_CARD)).get_result(result.application_id)

    assert dto is not None
    assert dto.score == result.score
    assert dto.grade == result.grade
    assert dto.data_completeness == result.data_completeness
    assert set(dto.flags) == set(result.flags)
    assert len(dto.factors) == len(result.factors)
    cash_gap = next(f for f in dto.factors if f.code == "cash_gap")
    assert cash_gap.points == -15


async def test_replay_is_bit_exact(session_factory: async_sessionmaker[AsyncSession]) -> None:
    result, stored = _result()
    async with session_factory() as session:
        await SqlAlchemyScoringRepository(session).add(result, input_snapshot=stored)
        await session.commit()

    async with session_factory() as session:
        record = (await session.scalars(select(ScoringResultRecord))).one()
        db_input = dict(record.input_snapshot)

    assert input_hash(db_input) == result.input_hash
    replay = _CARD.calculate(load_input(db_input))
    assert replay.score == result.score
    assert [(f.code, f.points) for f in replay.factors] == [
        (f.code, f.points) for f in result.factors
    ]


async def test_estimate_does_not_write(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        facade = ScoringFacadeImpl(session, FixedModel(_CARD))
        estimate = await facade.estimate(
            CompanyProfileDTO(
                legal_form="LLC",
                business_age_months=72,
                okved_main="56.10",
                annual_revenue=Decimal("48000000"),
                previous_annual_revenue=Decimal("40000000"),
                verification_status="verified",
                registry_status="active",
            )
        )
        rows = (await session.scalars(select(ScoringResultRecord))).all()

    assert rows == []
    assert estimate.grade in {"A", "B", "C", "D", "E"}
    assert estimate.score > 0


async def test_get_result_none_when_absent(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        dto = await ScoringFacadeImpl(session, FixedModel(_CARD)).get_result(uuid4())
    assert dto is None
