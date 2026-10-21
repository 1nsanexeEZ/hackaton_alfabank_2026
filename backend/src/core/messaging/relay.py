"""Outbox relay: publishes staged messages to Kafka in the order they were written."""

import asyncio
import logging
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.domain.clock import Clock
from src.core.messaging.outbox import OutboxRecord

logger = logging.getLogger(__name__)


class OutboxPublisher(Protocol):
    async def publish(
        self, topic: str, key: str, envelope: dict[str, Any], headers: dict[str, str]
    ) -> None: ...


class OutboxRelay:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        publisher: OutboxPublisher,
        clock: Clock,
        batch_size: int = 100,
        idle_delay_seconds: float = 0.2,
        error_delay_seconds: float = 2.0,
    ) -> None:
        self._session_factory = session_factory
        self._publisher = publisher
        self._clock = clock
        self._batch_size = batch_size
        self._idle_delay = idle_delay_seconds
        self._error_delay = error_delay_seconds

    async def publish_batch(self) -> int:
        """Publish one batch, returns how many messages went out.

        FOR UPDATE SKIP LOCKED lets several backend replicas run relays without
        publishing the same record twice. On the first failure the batch stops,
        so a later message never overtakes an earlier one.
        """
        published = 0
        async with self._session_factory() as session:
            stmt = (
                select(OutboxRecord)
                .where(OutboxRecord.published_at.is_(None))
                .order_by(OutboxRecord.id)
                .limit(self._batch_size)
                .with_for_update(skip_locked=True)
            )
            records = (await session.execute(stmt)).scalars().all()
            for record in records:
                try:
                    await self._publisher.publish(
                        record.topic,
                        record.key,
                        record.envelope,
                        {"event_id": str(record.event_id), "type": record.message_type},
                    )
                except Exception as exc:
                    record.attempts += 1
                    record.last_error = repr(exc)[:2000]
                    logger.warning("Outbox publish of %s failed: %s", record.event_id, exc)
                    break
                record.published_at = self._clock.now()
                published += 1
            await session.commit()
        return published

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                published = await self.publish_batch()
            except Exception:
                logger.exception("Outbox relay iteration failed")
                await _wait(stop, self._error_delay)
                continue
            if published == 0:
                await _wait(stop, self._idle_delay)


async def _wait(stop: asyncio.Event, seconds: float) -> None:
    try:
        await asyncio.wait_for(stop.wait(), timeout=seconds)
    except TimeoutError:
        pass
