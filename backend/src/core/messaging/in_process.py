"""Running the message flow without Kafka: the relay hands messages to an
in-process bus that delivers them to the same Subscriptions. Used by tests and
by local runs without a broker; ordering and idempotency rules stay the same."""

import asyncio
import logging
from collections import deque
from collections.abc import Sequence
from typing import Any

from src.core.messaging.relay import OutboxRelay
from src.core.messaging.subscriber import MessageProcessor, Subscription

logger = logging.getLogger(__name__)


class InProcessBus:
    """Collects published messages and delivers them after the relay commits,
    so a handler never runs inside the relay's transaction."""

    def __init__(self, subscriptions: Sequence[Subscription]) -> None:
        self._processor: MessageProcessor | None = None
        self._subscriptions = list(subscriptions)
        self._pending: deque[tuple[str, dict[str, Any]]] = deque()
        self.dead_letters: list[dict[str, Any]] = []
        self.published: list[tuple[str, str, dict[str, Any]]] = []

    def bind(self, processor: MessageProcessor) -> None:
        """The processor needs the bus as its dead letter sink, hence the late binding."""
        self._processor = processor

    async def publish(
        self, topic: str, key: str, envelope: dict[str, Any], headers: dict[str, str]
    ) -> None:
        self.published.append((topic, key, envelope))
        self._pending.append((topic, envelope))

    async def publish_dead_letter(self, topic: str, body: dict[str, Any], error: str) -> None:
        self.dead_letters.append({"topic": topic, "error": error, "message": body})

    async def deliver_pending(self) -> int:
        if self._processor is None:
            raise RuntimeError("InProcessBus.bind() was not called")
        delivered = 0
        while self._pending:
            topic, envelope = self._pending.popleft()
            for subscription in self._subscriptions:
                if subscription.topic == topic:
                    await self._processor.process(subscription, envelope)
                    delivered += 1
        return delivered


async def drain(relay: OutboxRelay, bus: InProcessBus, max_rounds: int = 100) -> int:
    """Publish and deliver until nothing is left, returns the number of rounds."""
    for round_number in range(1, max_rounds + 1):
        published = await relay.publish_batch()
        delivered = await bus.deliver_pending()
        if published == 0 and delivered == 0:
            return round_number
    raise RuntimeError(f"Message flow did not settle after {max_rounds} rounds")


async def run_in_process(
    relay: OutboxRelay, bus: InProcessBus, stop: asyncio.Event, idle_delay_seconds: float = 0.2
) -> None:
    while not stop.is_set():
        try:
            await drain(relay, bus)
        except Exception:
            logger.exception("In-process message flow iteration failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=idle_delay_seconds)
        except TimeoutError:
            pass
