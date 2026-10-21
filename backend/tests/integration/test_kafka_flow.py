"""Outbox -> relay -> Kafka -> subscriber -> inbox on a real broker (Docker)."""

import json
from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
from aiokafka import AIOKafkaConsumer
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.config import Settings
from src.core.domain.clock import FrozenClock
from src.core.facades import FacadeRegistry
from src.core.messaging import topics
from src.core.messaging.contracts.process import ProcessCompleted
from src.core.messaging.outbox import SqlAlchemyOutboxWriter
from src.core.messaging.runtime import MessagingRuntime
from src.core.messaging.subscriber import HandlerContext, Subscription
from tests.helpers import wait_for

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def kafka_servers() -> Iterator[str]:
    from testcontainers.kafka import KafkaContainer

    with KafkaContainer() as kafka:
        yield kafka.get_bootstrap_server()


async def read_one(servers: str, topic: str, timeout_ms: int = 30_000) -> dict:
    consumer = AIOKafkaConsumer(
        topic, bootstrap_servers=servers, auto_offset_reset="earliest", group_id=None
    )
    await consumer.start()
    try:
        batch = await consumer.getmany(timeout_ms=timeout_ms, max_records=1)
        records = [record for records in batch.values() for record in records]
        assert records, f"nothing in {topic}"
        return json.loads(records[0].value)
    finally:
        await consumer.stop()


async def test_message_goes_through_kafka_once(
    session_factory: async_sessionmaker[AsyncSession], kafka_servers: str
) -> None:
    clock = FrozenClock()
    received: list[UUID] = []

    async def handler(ctx: HandlerContext, event: ProcessCompleted) -> None:
        received.append(event.application_id)

    runtime = MessagingRuntime(
        Settings(
            _env_file=None,
            messaging_mode="kafka",
            kafka_bootstrap_servers=kafka_servers,
            kafka_topic_partitions=1,
        ),
        session_factory,
        FacadeRegistry(),
        clock,
        [Subscription("projector", topics.PROCESS_EVENTS, "projector.integration", handler)],
    )
    await runtime.start()
    try:
        application_id = uuid4()
        async with session_factory() as session:
            await SqlAlchemyOutboxWriter(session, "process", clock).add(
                ProcessCompleted(
                    process_id=uuid4(), application_id=application_id, outcome="APPROVE"
                ),
                key=application_id,
                correlation_id=application_id,
            )
            await session.commit()

        async def delivered() -> bool:
            return received == [application_id]

        await wait_for(delivered, seconds=60)

        # at-least-once: a redelivered envelope is ignored by the inbox
        envelope = await read_one(kafka_servers, topics.PROCESS_EVENTS)
        assert runtime.broker is not None
        await runtime.broker.publish(
            envelope, topics.PROCESS_EVENTS, key=str(application_id).encode()
        )

        # a poison message ends up in the DLQ instead of blocking the partition
        await runtime.broker.publish(b"not json", topics.PROCESS_EVENTS)
        dead = await read_one(kafka_servers, topics.dead_letter_topic(topics.PROCESS_EVENTS))
        assert dead["topic"] == topics.PROCESS_EVENTS
        assert received == [application_id]
    finally:
        await runtime.stop()
