"""The whole message flow without Kafka: command -> handler -> reply -> handler."""

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.config import Settings
from src.core.domain.clock import FrozenClock
from src.core.facades import FacadeRegistry
from src.core.messaging import topics
from src.core.messaging.contracts.process import ProcessCompleted
from src.core.messaging.contracts.scoring import CalculateScore, ScoreCalculated
from src.core.messaging.outbox import SqlAlchemyOutboxWriter
from src.core.messaging.runtime import MessagingRuntime, validate_subscriptions
from src.core.messaging.subscriber import HandlerContext, Subscription


async def test_command_and_reply_are_delivered_in_process(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    clock = FrozenClock()
    received: list[str] = []

    async def scoring_handler(ctx: HandlerContext, command: CalculateScore) -> None:
        received.append("scoring")
        await ctx.outbox.add(
            ScoreCalculated(
                application_id=command.application_id,
                result_id=uuid4(),
                score=790,
                risk_grade="A",
            ),
            key=command.application_id,
            correlation_id=ctx.envelope.correlation_id,
            causation_id=ctx.envelope.event_id,
        )

    async def process_handler(ctx: HandlerContext, event: ScoreCalculated) -> None:
        received.append(f"process:{event.risk_grade}")
        assert ctx.envelope.causation_id is not None

    runtime = MessagingRuntime(
        Settings(_env_file=None, messaging_mode="manual"),
        session_factory,
        FacadeRegistry(),
        clock,
        [
            Subscription("scoring", topics.SCORING_COMMANDS, "scoring.commands", scoring_handler),
            Subscription("process", topics.SCORING_EVENTS, "process.engine", process_handler),
        ],
    )
    await runtime.start()

    application_id = uuid4()
    async with session_factory() as session:
        await SqlAlchemyOutboxWriter(session, "process", clock).add(
            CalculateScore(application_id=application_id),
            key=application_id,
            correlation_id=application_id,
        )
        await session.commit()

    await runtime.drain()
    await runtime.stop()

    assert received == ["scoring", "process:A"]
    assert runtime.bus is not None and runtime.bus.dead_letters == []
    assert [topic for topic, *_ in runtime.bus.published] == [
        topics.SCORING_COMMANDS,
        topics.SCORING_EVENTS,
    ]


async def test_failing_handler_ends_in_dead_letters(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    clock = FrozenClock()

    async def broken(ctx: HandlerContext, event: ProcessCompleted) -> None:
        raise RuntimeError("bug")

    runtime = MessagingRuntime(
        Settings(_env_file=None, messaging_mode="manual"),
        session_factory,
        FacadeRegistry(),
        clock,
        [Subscription("projector", topics.PROCESS_EVENTS, "projector.read-models", broken)],
    )
    await runtime.start()
    application_id = uuid4()
    async with session_factory() as session:
        await SqlAlchemyOutboxWriter(session, "process", clock).add(
            ProcessCompleted(process_id=uuid4(), application_id=application_id, outcome="APPROVE"),
            key=application_id,
            correlation_id=application_id,
        )
        await session.commit()
    await runtime.drain()
    await runtime.stop()

    assert runtime.bus is not None
    assert len(runtime.bus.dead_letters) == 1
    assert "bug" in runtime.bus.dead_letters[0]["error"]


async def noop(ctx: HandlerContext, message: object) -> None:
    return None


def test_unknown_topic_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown topic"):
        validate_subscriptions([Subscription("x", "no.such.topic", "x.y", noop)])


def test_duplicate_group_is_rejected() -> None:
    with pytest.raises(ValueError, match="Duplicate consumer group"):
        validate_subscriptions(
            [
                Subscription("a", topics.PROCESS_EVENTS, "same.group", noop),
                Subscription("a", topics.DECISION_EVENTS, "same.group", noop),
            ]
        )
