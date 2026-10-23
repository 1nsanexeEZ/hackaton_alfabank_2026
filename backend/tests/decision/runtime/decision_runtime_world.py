"""Мир runtime-тестов decision: настоящие use case, репозитории и SQLite, соседи — фейки из мира
golden-тестов политики (`tests/decision/unit/decision_world.py`, данные демо §9).

Каждый вызов use case — в своей сессии с commit, как это делает обработчик сообщений.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.domain.clock import FrozenClock
from src.core.messaging.contracts.decision import (
    CheckStopFactors,
    MakeDecision,
    ManualTerms,
    RecordManualDecision,
    RequestedInfo,
)
from src.modules.decision.application.check_stop_factors import CheckStopFactorsUseCase
from src.modules.decision.application.make_decision import MakeDecisionUseCase
from src.modules.decision.application.record_manual_decision import RecordManualDecisionUseCase
from src.modules.decision.domain.policy import CreditPolicy
from src.modules.decision.domain.result import DecisionResult
from src.modules.decision.facade import ClientDecisionDTO, DecisionDTO
from src.modules.decision.infrastructure.config_loader import default_policy
from src.modules.decision.infrastructure.facade_impl import DecisionFacadeImpl
from src.modules.decision.infrastructure.models import DecisionResultRecord
from src.modules.decision.infrastructure.repository import SqlAlchemyDecisionRepository
from tests.decision.unit.decision_world import NOW, DecisionWorld
from tests.fakes.messaging import FakeOutboxWriter

KEY_RATE = Decimal("16.50")
UNDERWRITER = UUID("00000000-0000-4000-8000-0000000000aa")
TASK = UUID("00000000-0000-4000-8000-0000000000bb")

Sessions = async_sessionmaker[AsyncSession]


async def make_decision(
    sessions: Sessions,
    world: DecisionWorld,
    event_id: UUID | None = None,
    policy: CreditPolicy | None = None,
) -> FakeOutboxWriter:
    policy = policy or default_policy()
    outbox = FakeOutboxWriter()
    async with sessions() as session:
        use_case = MakeDecisionUseCase(
            SqlAlchemyDecisionRepository(session),
            policy,
            world.builder(policy),
            world.products,
            FrozenClock(NOW),
            KEY_RATE,
        )
        await use_case.execute(
            MakeDecision(application_id=world.application_id),
            command_event_id=event_id or uuid4(),
            outbox=outbox,
        )
        await session.commit()
    return outbox


async def check_stop_factors(
    sessions: Sessions, world: DecisionWorld, event_id: UUID | None = None
) -> FakeOutboxWriter:
    policy = default_policy()
    outbox = FakeOutboxWriter()
    async with sessions() as session:
        use_case = CheckStopFactorsUseCase(
            SqlAlchemyDecisionRepository(session),
            policy,
            world.builder(policy),
            FrozenClock(NOW),
            KEY_RATE,
        )
        await use_case.execute(
            CheckStopFactors(application_id=world.application_id),
            command_event_id=event_id or uuid4(),
            outbox=outbox,
        )
        await session.commit()
    return outbox


def manual_command(
    world: DecisionWorld,
    outcome: str,
    *,
    amount: str | None = None,
    term: int = 24,
    rate: str = "25",
    conditions: tuple[str, ...] = (),
    documents: tuple[str, ...] = (),
    comment: str = "Проверил выписку и договоры, риск приемлемый",
) -> RecordManualDecision:
    return RecordManualDecision(
        application_id=world.application_id,
        task_id=TASK,
        underwriter_id=UNDERWRITER,
        outcome=outcome,  # type: ignore[arg-type]
        terms=ManualTerms(
            amount=Decimal(amount),
            term_months=term,
            rate=Decimal(rate),
            conditions=list(conditions),
        )
        if amount is not None
        else None,
        requested_info=RequestedInfo(
            documents=list(documents), comment="Приложите договор аренды склада."
        )
        if documents
        else None,
        comment=comment,
    )


async def record_manual(
    sessions: Sessions,
    world: DecisionWorld,
    command: RecordManualDecision,
    event_id: UUID | None = None,
) -> FakeOutboxWriter:
    outbox = FakeOutboxWriter()
    async with sessions() as session:
        use_case = RecordManualDecisionUseCase(
            SqlAlchemyDecisionRepository(session),
            default_policy(),
            world.applications,
            world.products,
            FrozenClock(NOW),
            KEY_RATE,
        )
        await use_case.execute(command, command_event_id=event_id or uuid4(), outbox=outbox)
        await session.commit()
    return outbox


async def decision(sessions: Sessions, application_id: UUID) -> DecisionDTO | None:
    async with sessions() as session:
        return await DecisionFacadeImpl(session, FrozenClock(NOW)).get_decision(application_id)


async def client_view(sessions: Sessions, application_id: UUID) -> ClientDecisionDTO | None:
    async with sessions() as session:
        return await DecisionFacadeImpl(session, FrozenClock(NOW)).get_client_view(application_id)


async def by_command(sessions: Sessions, event_id: UUID) -> DecisionResult | None:
    async with sessions() as session:
        return await SqlAlchemyDecisionRepository(session).get_by_command(event_id)


async def stored_count(sessions: Sessions, application_id: UUID) -> int:
    async with sessions() as session:
        stmt = select(func.count()).where(DecisionResultRecord.application_id == application_id)
        return (await session.scalars(stmt)).one()
