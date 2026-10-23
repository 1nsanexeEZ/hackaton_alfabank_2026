"""Rebuild the projector read models from Kafka.

Clears the projector tables, then reads applications/process/decision/clients
events from the very beginning with a fresh consumer group
(`projector.read-models.rebuild-<UTC timestamp>`, auto_offset_reset=earliest)
and applies them with the same projection as the live consumer. Stops once it
reaches the end offsets taken at start; later events are the live consumer's.

The rebuild writes into the same tables, the live consumer may keep running:
both only upsert and recompute, so they converge. Until the rebuild catches up
the lists are incomplete.

Run from backend/ (DATABASE_URL and KAFKA_BOOTSTRAP_SERVERS as for the app):

    uv run python -m scripts.projector_rebuild
"""

import asyncio
import logging
import sys
import time
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any, Protocol

from aiokafka import AIOKafkaConsumer, TopicPartition

from src.core.config import Settings, get_settings
from src.core.http.request_id import configure_logging
from src.core.infrastructure.database.session import build_engine, build_session_factory
from src.modules.projector.infrastructure.consumer import GROUP_PREFIX, PROJECTED_TOPICS
from src.modules.projector.infrastructure.rebuild import RebuildStats, rebuild

logger = logging.getLogger("projector.rebuild")


class Consumer(Protocol):
    """The part of AIOKafkaConsumer the reader needs."""

    def assignment(self) -> set[TopicPartition]: ...

    async def getmany(
        self, *partitions: TopicPartition, timeout_ms: int = 0, max_records: int | None = None
    ) -> dict[TopicPartition, list[Any]]: ...

    async def end_offsets(self, partitions: list[TopicPartition]) -> dict[TopicPartition, int]: ...

    async def position(self, partition: TopicPartition) -> int: ...


def rebuild_group_id(now: datetime | None = None) -> str:
    moment = now or datetime.now(UTC)
    return f"{GROUP_PREFIX}.rebuild-{moment:%Y%m%d%H%M%S}"


async def read_until_caught_up(
    consumer: Consumer,
    poll_timeout_ms: int = 1000,
    max_records: int = 500,
    assignment_timeout_s: float = 60.0,
) -> AsyncIterator[bytes]:
    """Yield message bodies until every assigned partition reaches the end
    offset it had when the assignment arrived."""
    end_offsets: dict[TopicPartition, int] | None = None
    deadline = time.monotonic() + assignment_timeout_s
    while True:
        batch = await consumer.getmany(timeout_ms=poll_timeout_ms, max_records=max_records)
        for records in batch.values():
            for record in records:
                yield record.value
        if end_offsets is None:
            assignment = consumer.assignment()
            if not assignment:
                if time.monotonic() > deadline:
                    raise RuntimeError("No partitions assigned: are the topics created?")
                continue
            end_offsets = await consumer.end_offsets(sorted(assignment))
        positions = {tp: await consumer.position(tp) for tp in end_offsets}
        if all(positions[tp] >= end for tp, end in end_offsets.items()):
            return


async def run(settings: Settings) -> RebuildStats:
    from src.main import create_app  # wires the facades of every module

    app = create_app(settings)
    engine = build_engine(settings.database_url)
    group_id = rebuild_group_id()
    consumer = AIOKafkaConsumer(
        *PROJECTED_TOPICS,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=group_id,
        client_id="projector-rebuild",
        auto_offset_reset="earliest",
        enable_auto_commit=False,
    )
    logger.info("Rebuilding read models with consumer group %s", group_id)
    await consumer.start()
    try:
        stats = await rebuild(
            build_session_factory(engine), app.state.facades, read_until_caught_up(consumer)
        )
        await consumer.commit()
    finally:
        await consumer.stop()
        await engine.dispose()
    logger.info(
        "Rebuild done: %s applied, %s skipped, %s failed",
        stats.applied,
        stats.skipped,
        stats.failed,
    )
    return stats


def main() -> int:
    configure_logging()
    stats = asyncio.run(run(get_settings()))
    return 1 if stats.failed else 0


if __name__ == "__main__":
    sys.exit(main())
