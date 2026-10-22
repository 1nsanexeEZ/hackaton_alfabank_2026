from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.scoring.application.serialization import dump_input, input_hash, load_input
from src.scoring.domain.model import ScoringResult
from src.scoring.facade import CompanyProfileDTO
from src.scoring.infrastructure.config_loader import load_scorecard
from src.scoring.infrastructure.facade_impl import ScoringFacadeImpl
from src.scoring.infrastructure.models import ScoringResultRecord
from src.scoring.infrastructure.repository import SqlAlchemyScoringRepository
from tests.scoring.scenarios import SCENARIOS

_NOW = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)
_CARD = load_scorecard()


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
        dto = await ScoringFacadeImpl(session, _CARD).get_result(result.application_id)

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
        facade = ScoringFacadeImpl(session, _CARD)
        estimate = facade.estimate(
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
        dto = await ScoringFacadeImpl(session, _CARD).get_result(uuid4())
    assert dto is None
