import json
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.domain.clock import FrozenClock
from src.core.facades import FacadeRegistry
from src.core.messaging import topics
from src.core.messaging.contracts.applications import StartReview
from src.core.messaging.contracts.process import StepCompleted
from src.core.messaging.inbox import InboxRecord
from src.core.messaging.outbox import OutboxRecord
from src.core.messaging.subscriber import HandlerContext, MessageProcessor, Subscription
from tests.core.messaging.conftest import RecordingDeadLetters, step_envelope


class Recorder:
    def __init__(self, fail_times: int = 0) -> None:
        self.calls: list[StepCompleted] = []
        self.fail_times = fail_times

    async def __call__(self, ctx: HandlerContext, message: StepCompleted) -> None:
        self.calls.append(message)
        # the handler's own changes go through the context and commit with the inbox mark
        await ctx.outbox.add(
            StartReview(application_id=message.application_id),
            key=message.application_id,
            correlation_id=ctx.envelope.correlation_id,
            causation_id=ctx.envelope.event_id,
        )
        if len(self.calls) <= self.fail_times:
            raise RuntimeError("temporary failure")


def subscription(handler: Any, message_types: frozenset[str] | None = None) -> Subscription:
    return Subscription(
        module="process",
        topic=topics.PROCESS_EVENTS,
        group_id="process.test",
        handler=handler,
        message_types=message_types,
    )


def processor(
    session_factory: async_sessionmaker[AsyncSession],
    clock: FrozenClock,
    dead_letters: RecordingDeadLetters,
) -> MessageProcessor:
    sleeps: list[float] = []

    async def no_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    return MessageProcessor(
        session_factory, FacadeRegistry(), clock, dead_letters, (0.5, 1.0, 2.0), sleep=no_sleep
    )


async def count(session_factory: async_sessionmaker[AsyncSession], model: Any) -> int:
    async with session_factory() as session:
        return (await session.execute(select(func.count()).select_from(model))).scalar_one()


async def test_processes_and_commits_handler_changes_with_inbox(
    session_factory: async_sessionmaker[AsyncSession],
    clock: FrozenClock,
    dead_letters: RecordingDeadLetters,
) -> None:
    handler = Recorder()
    envelope = step_envelope()
    outcome = await processor(session_factory, clock, dead_letters).process(
        subscription(handler), envelope
    )
    assert outcome == "processed"
    assert isinstance(handler.calls[0], StepCompleted)
    assert await count(session_factory, InboxRecord) == 1
    async with session_factory() as session:
        reply = (await session.execute(select(OutboxRecord))).scalar_one()
    assert reply.envelope["causation_id"] == envelope["event_id"]
    assert reply.envelope["producer"] == "process"


async def test_duplicate_is_ignored(
    session_factory: async_sessionmaker[AsyncSession],
    clock: FrozenClock,
    dead_letters: RecordingDeadLetters,
) -> None:
    handler = Recorder()
    envelope = step_envelope()
    proc = processor(session_factory, clock, dead_letters)
    assert await proc.process(subscription(handler), envelope) == "processed"
    assert await proc.process(subscription(handler), envelope) == "duplicate"
    assert len(handler.calls) == 1
    assert await count(session_factory, OutboxRecord) == 1


async def test_accepts_raw_bytes(
    session_factory: async_sessionmaker[AsyncSession],
    clock: FrozenClock,
    dead_letters: RecordingDeadLetters,
) -> None:
    handler = Recorder()
    body = json.dumps(step_envelope()).encode()
    assert (
        await processor(session_factory, clock, dead_letters).process(subscription(handler), body)
        == "processed"
    )


async def test_other_message_types_are_skipped(
    session_factory: async_sessionmaker[AsyncSession],
    clock: FrozenClock,
    dead_letters: RecordingDeadLetters,
) -> None:
    handler = Recorder()
    outcome = await processor(session_factory, clock, dead_letters).process(
        subscription(handler, frozenset({"ProcessCompleted"})), step_envelope()
    )
    assert outcome == "skipped"
    assert handler.calls == []


@pytest.mark.parametrize(
    "body",
    [
        b"not json",
        {"type": "StepCompleted"},
        {**step_envelope(), "type": "NoSuchMessage"},
        {**step_envelope(), "payload": {"application_id": "not-a-uuid"}},
    ],
    ids=["garbage", "no-envelope", "unknown-type", "invalid-payload"],
)
async def test_poison_message_goes_to_dlq_without_retries(
    session_factory: async_sessionmaker[AsyncSession],
    clock: FrozenClock,
    dead_letters: RecordingDeadLetters,
    body: Any,
) -> None:
    handler = Recorder()
    outcome = await processor(session_factory, clock, dead_letters).process(
        subscription(handler), body
    )
    assert outcome == "dead_letter"
    assert handler.calls == []
    assert dead_letters.items[0]["topic"] == topics.PROCESS_EVENTS
    assert dead_letters.items[0]["error"]


async def test_temporary_failure_is_retried(
    session_factory: async_sessionmaker[AsyncSession],
    clock: FrozenClock,
    dead_letters: RecordingDeadLetters,
) -> None:
    handler = Recorder(fail_times=2)
    outcome = await processor(session_factory, clock, dead_letters).process(
        subscription(handler), step_envelope()
    )
    assert outcome == "processed"
    assert len(handler.calls) == 3
    # failed attempts left nothing behind: one reply, one inbox mark
    assert await count(session_factory, OutboxRecord) == 1
    assert await count(session_factory, InboxRecord) == 1
    assert dead_letters.items == []


async def test_persistent_failure_goes_to_dlq_and_rolls_back(
    session_factory: async_sessionmaker[AsyncSession],
    clock: FrozenClock,
    dead_letters: RecordingDeadLetters,
) -> None:
    handler = Recorder(fail_times=100)
    envelope = step_envelope()
    outcome = await processor(session_factory, clock, dead_letters).process(
        subscription(handler), envelope
    )
    assert outcome == "dead_letter"
    assert len(handler.calls) == 3
    assert await count(session_factory, OutboxRecord) == 0
    assert await count(session_factory, InboxRecord) == 0
    assert dead_letters.items[0]["body"]["event_id"] == envelope["event_id"]
    assert "temporary failure" in dead_letters.items[0]["error"]


async def test_handler_gets_facades_bound_to_its_session(
    session_factory: async_sessionmaker[AsyncSession],
    clock: FrozenClock,
    dead_letters: RecordingDeadLetters,
) -> None:
    class Lookup:
        def __init__(self, session: AsyncSession) -> None:
            self.session = session

    registry = FacadeRegistry()
    registry.register(Lookup, Lookup)
    seen: list[bool] = []

    async def handler(ctx: HandlerContext, message: StepCompleted) -> None:
        seen.append(ctx.facade(Lookup).session is ctx.session)

    proc = MessageProcessor(session_factory, registry, clock, dead_letters)
    assert await proc.process(subscription(handler), step_envelope(event_id=uuid4())) == "processed"
    assert seen == [True]
