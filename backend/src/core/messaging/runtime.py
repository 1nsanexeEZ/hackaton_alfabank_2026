"""Starts and stops the message flow for the configured mode."""

import asyncio
import contextlib
import logging
from collections.abc import Sequence

from faststream.kafka import KafkaBroker
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.config import Settings
from src.core.domain.clock import Clock
from src.core.facades import FacadeRegistry
from src.core.messaging.broker import (
    KafkaDeadLetterPublisher,
    KafkaOutboxPublisher,
    attach,
    create_broker,
    ensure_topics,
)
from src.core.messaging.in_process import InProcessBus, drain, run_in_process
from src.core.messaging.relay import OutboxRelay
from src.core.messaging.subscriber import MessageProcessor, Subscription
from src.core.messaging.topics import ALL_TOPICS

logger = logging.getLogger(__name__)


def validate_subscriptions(subscriptions: Sequence[Subscription]) -> None:
    group_ids: set[str] = set()
    for subscription in subscriptions:
        if subscription.topic not in ALL_TOPICS:
            raise ValueError(f"Unknown topic {subscription.topic!r} in {subscription.group_id}")
        if subscription.group_id in group_ids:
            raise ValueError(f"Duplicate consumer group {subscription.group_id!r}")
        group_ids.add(subscription.group_id)


class MessagingRuntime:
    def __init__(
        self,
        settings: Settings,
        session_factory: async_sessionmaker[AsyncSession],
        facades: FacadeRegistry,
        clock: Clock,
        subscriptions: Sequence[Subscription],
    ) -> None:
        validate_subscriptions(subscriptions)
        self.mode = settings.messaging_mode
        self._settings = settings
        self._session_factory = session_factory
        self._facades = facades
        self._clock = clock
        self._subscriptions = list(subscriptions)
        self._stop = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self.broker: KafkaBroker | None = None
        self.bus: InProcessBus | None = None
        self.relay: OutboxRelay | None = None

    async def start(self) -> None:
        if self.mode == "kafka":
            await self._start_kafka()
        else:
            self._start_in_process()

    async def _start_kafka(self) -> None:
        servers = self._settings.kafka_bootstrap_servers
        if self._settings.kafka_create_topics:
            await ensure_topics(servers, self._settings.kafka_topic_partitions)
        self.broker = create_broker(servers)
        processor = MessageProcessor(
            self._session_factory, self._facades, self._clock, KafkaDeadLetterPublisher(self.broker)
        )
        for subscription in self._subscriptions:
            attach(self.broker, processor, subscription)
        await self.broker.start()
        self.relay = self._build_relay(KafkaOutboxPublisher(self.broker))
        self._task = asyncio.create_task(self.relay.run(self._stop), name="outbox-relay")
        logger.info("Kafka messaging started, %s subscriptions", len(self._subscriptions))

    def _start_in_process(self) -> None:
        self.bus = InProcessBus(self._subscriptions)
        self.bus.bind(
            MessageProcessor(
                self._session_factory,
                self._facades,
                self._clock,
                self.bus,
                backoff_seconds=(0.0,),
            )
        )
        self.relay = self._build_relay(self.bus)
        if self.mode == "in_process":
            self._task = asyncio.create_task(
                run_in_process(self.relay, self.bus, self._stop), name="in-process-messaging"
            )

    def _build_relay(self, publisher: KafkaOutboxPublisher | InProcessBus) -> OutboxRelay:
        return OutboxRelay(
            self._session_factory,
            publisher,
            self._clock,
            batch_size=self._settings.outbox_batch_size,
        )

    async def drain(self) -> int:
        """Deliver everything staged so far (manual and in_process modes)."""
        if self.relay is None or self.bus is None:
            raise RuntimeError("drain() works only without Kafka")
        return await drain(self.relay, self.bus)

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        if self.broker is not None:
            await self.broker.stop()
