from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.domain.clock import FrozenClock
from src.core.messaging.contracts.applications import StartReview
from src.core.messaging.outbox import OutboxRecord, SqlAlchemyOutboxWriter
from src.core.messaging.relay import OutboxRelay


class Publisher:
    def __init__(self, fail_on: int | None = None) -> None:
        self.sent: list[tuple[str, str, dict[str, Any], dict[str, str]]] = []
        self.fail_on = fail_on
        self.attempts = 0

    async def publish(
        self, topic: str, key: str, envelope: dict[str, Any], headers: dict[str, str]
    ) -> None:
        self.attempts += 1
        if self.fail_on is not None and self.attempts == self.fail_on:
            raise ConnectionError("broker is down")
        self.sent.append((topic, key, envelope, headers))


async def stage(session_factory: async_sessionmaker[AsyncSession], count: int) -> list[str]:
    ids = []
    async with session_factory() as session:
        writer = SqlAlchemyOutboxWriter(session, "process", FrozenClock())
        for _ in range(count):
            application_id = uuid4()
            event_id = await writer.add(
                StartReview(application_id=application_id),
                key=application_id,
                correlation_id=application_id,
            )
            ids.append(str(event_id))
        await session.commit()
    return ids


async def test_publishes_in_order_and_marks_published(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    ids = await stage(session_factory, 3)
    publisher = Publisher()
    relay = OutboxRelay(session_factory, publisher, FrozenClock())

    assert await relay.publish_batch() == 3
    assert [headers["event_id"] for *_, headers in publisher.sent] == ids
    topic, key, envelope, headers = publisher.sent[0]
    assert topic == "applications.commands"
    assert envelope["event_id"] == ids[0] and key == envelope["payload"]["application_id"]
    assert headers["type"] == "StartReview"
    # nothing left to publish
    assert await relay.publish_batch() == 0


async def test_failure_stops_the_batch_and_keeps_order(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    ids = await stage(session_factory, 3)
    publisher = Publisher(fail_on=2)
    relay = OutboxRelay(session_factory, publisher, FrozenClock())

    assert await relay.publish_batch() == 1
    async with session_factory() as session:
        records = (await session.execute(select(OutboxRecord).order_by(OutboxRecord.id))).scalars()
        states = [(r.published_at is not None, r.attempts, bool(r.last_error)) for r in records]
    assert states == [(True, 0, False), (False, 1, True), (False, 0, False)]

    assert await relay.publish_batch() == 2
    assert [headers["event_id"] for *_, headers in publisher.sent] == ids


async def test_batch_size_is_respected(session_factory: async_sessionmaker[AsyncSession]) -> None:
    await stage(session_factory, 5)
    relay = OutboxRelay(session_factory, Publisher(), FrozenClock(), batch_size=2)
    assert [await relay.publish_batch() for _ in range(4)] == [2, 2, 1, 0]
