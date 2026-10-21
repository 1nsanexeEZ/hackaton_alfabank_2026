"""Kafka wiring: broker, topic creation, outbox publisher, dead letters and
attaching Subscriptions as FastStream subscribers."""

import logging
from datetime import UTC, datetime
from typing import Any

from aiokafka.admin import AIOKafkaAdminClient, NewTopic
from faststream import AckPolicy
from faststream.kafka import KafkaBroker, KafkaMessage

from src.core.messaging.subscriber import MessageProcessor, Subscription
from src.core.messaging.topics import ALL_TOPICS_WITH_DLQ, dead_letter_topic

logger = logging.getLogger(__name__)

CLIENT_ID = "credit-backend"


def create_broker(bootstrap_servers: str) -> KafkaBroker:
    return KafkaBroker(bootstrap_servers, client_id=CLIENT_ID)


async def ensure_topics(
    bootstrap_servers: str, partitions: int, replication_factor: int = 1
) -> list[str]:
    """Create missing topics (and their DLQs), returns the created names."""
    admin = AIOKafkaAdminClient(bootstrap_servers=bootstrap_servers, client_id=CLIENT_ID)
    await admin.start()
    try:
        existing = set(await admin.list_topics())
        missing = [topic for topic in ALL_TOPICS_WITH_DLQ if topic not in existing]
        if missing:
            await admin.create_topics(
                [
                    NewTopic(
                        topic,
                        partitions,
                        replication_factor,
                        # Kept forever: the projector rebuilds read models from the start.
                        topic_configs={"retention.ms": "-1"},
                    )
                    for topic in missing
                ]
            )
            logger.info("Created Kafka topics: %s", ", ".join(missing))
        return missing
    finally:
        await admin.close()


class KafkaOutboxPublisher:
    def __init__(self, broker: KafkaBroker) -> None:
        self._broker = broker

    async def publish(
        self, topic: str, key: str, envelope: dict[str, Any], headers: dict[str, str]
    ) -> None:
        await self._broker.publish(envelope, topic, key=key.encode(), headers=headers)


class KafkaDeadLetterPublisher:
    def __init__(self, broker: KafkaBroker) -> None:
        self._broker = broker

    async def publish_dead_letter(self, topic: str, body: dict[str, Any], error: str) -> None:
        await self._broker.publish(
            {
                "topic": topic,
                "error": error,
                "failed_at": datetime.now(UTC).isoformat(),
                "message": body,
            },
            dead_letter_topic(topic),
        )


def attach(broker: KafkaBroker, processor: MessageProcessor, subscription: Subscription) -> None:
    """Register a Subscription as a FastStream subscriber.

    The processor never raises for a bad message (it goes to the DLQ), so an
    exception here means infrastructure trouble: the offset is not committed
    and Kafka redelivers the message.
    """

    async def consume(message: KafkaMessage) -> None:
        await processor.process(subscription, message.body)

    consume.__name__ = f"consume_{subscription.group_id.replace('.', '_').replace('-', '_')}"
    broker.subscriber(
        subscription.topic,
        group_id=subscription.group_id,
        auto_offset_reset="earliest",
        ack_policy=AckPolicy.NACK_ON_ERROR,
    )(consume)
