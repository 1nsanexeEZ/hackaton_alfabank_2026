"""Rebuild = incremental build.

The golden scenario is fed to the live consumer step by step while the
neighbours change their state; then the tables are cleared and the same events
are replayed through the rebuild path against the final state. Both must give
the same tables, equal to golden/read_models.json.
Regenerate the file after an intended change: UPDATE_GOLDEN=1 pytest tests/projector.
"""

import json
import os
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from aiokafka import TopicPartition
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from scripts import projector_rebuild
from src.modules.projector.infrastructure.rebuild import RebuildStats, rebuild
from tests.projector.golden_scenario import (
    A1,
    A2,
    A3,
    IVANOV,
    ROMASHKA,
    T2,
    T3,
    published,
    steps,
)
from tests.projector.unit.factories import overview
from tests.projector.world import Consumer, OpenFacade, OpenStore, World, dump_tables, stream

GOLDEN = Path(__file__).parent / "golden" / "read_models.json"


async def build_incrementally(
    session_factory: async_sessionmaker[AsyncSession], world: World
) -> list[dict[str, Any]]:
    consumer = Consumer(session_factory, world.registry)
    events = published(steps())
    changed: set[int] = set()
    for step, body in events:
        if step.change is not None and id(step) not in changed:
            changed.add(id(step))
            step.change(world)
        assert await consumer.deliver_envelope(body) == "processed", body["type"]
    # Kafka delivers at least once: a redelivered decision is a duplicate
    redelivered = next(body for _, body in events if body["type"] == "DecisionMade")
    assert await consumer.deliver_envelope(redelivered) == "duplicate"
    return [body for _, body in events] + [redelivered]


async def test_rebuild_gives_the_same_tables_as_the_live_consumer(
    session_factory: async_sessionmaker[AsyncSession], world: World, facade: OpenFacade
) -> None:
    bodies = await build_incrementally(session_factory, world)
    incremental = await dump_tables(session_factory)

    # Kafka gives bytes; the redelivered event is in the stream too, without an inbox
    stats = await rebuild(
        session_factory, world.registry, stream(json.dumps(b).encode() for b in bodies)
    )
    rebuilt = await dump_tables(session_factory)

    assert stats == RebuildStats(applied=len(bodies))
    assert rebuilt == incremental
    if os.environ.get("UPDATE_GOLDEN"):
        GOLDEN.write_text(
            json.dumps(incremental, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    assert incremental == json.loads(GOLDEN.read_text(encoding="utf-8"))

    # the same tables read through the facade, for the docs/sla.md figures
    async with facade() as projector:
        metrics = await projector.get_backoffice_metrics(date(2026, 10, 20), date(2026, 10, 21))
        queue = await projector.get_underwriting_queue("underwriter", status="open")
        closed = await projector.get_underwriting_queue("underwriter", status="closed")
        romashka = await projector.get_organization_dashboard(ROMASHKA)
        ivanov = await projector.get_organization_dashboard(IVANOV)
        a1 = await projector.get_timeline(A1, "client")
        a1_bank = await projector.get_timeline(A1, "bank")
        overview_a2 = (await projector.list_applications(ROMASHKA, status="offer_ready")).items
    assert (metrics.submitted, metrics.decided) == (4, 3)
    assert metrics.auto_decision_share == 0.6667  # A1 and A4 automatic, A2 by an underwriter
    assert metrics.avg_time_to_decision_sec == 3020.0  # (600 + 7260 + 1200) / 3
    assert [i.task_id for i in queue.items] == [T3]
    assert queue.items[0].routing_reasons == ("SHORT_BUSINESS_HISTORY",)
    assert queue.items[0].cash_gap is True and queue.items[0].overdue is False
    assert [(i.task_id, i.status, i.routing_reasons) for i in closed.items] == [(T2, "done", ())]
    assert romashka is not None and (
        romashka.active_applications,
        romashka.action_required_count,
    ) == (2, 2)
    assert ivanov is not None and ivanov.active_applications == 1
    assert (ivanov.pre_approved_max_amount, ivanov.pre_approved_rate_from) == (5000000, 22.5)
    assert [e.title for e in a1] == [
        "Заявка отправлена в банк",
        "Заявка на рассмотрении",
        "Проверяем данные о компании",
        "Кредит одобрен",
        "Готово предложение банка",
        "Предложение принято, идёт подписание",
    ]
    assert len(a1_bank) == len(a1) + 2  # the route start and an internal step
    assert [o.application_id for o in overview_a2] == [A2]
    assert A3 not in {o.application_id for o in overview_a2}


async def test_rebuild_clears_what_is_not_in_the_events(
    session_factory: async_sessionmaker[AsyncSession], world: World, store: OpenStore
) -> None:
    async with store() as s:
        await s.save_overview(overview())
    stats = await rebuild(
        session_factory, world.registry, stream([b"not json", {"type": "NoSuchEvent"}])
    )
    assert stats == RebuildStats(skipped=2)
    tables = await dump_tables(session_factory)
    assert all(rows == [] for rows in tables.values())


# --- reading Kafka until caught up ------------------------------------------------


class FakeKafkaConsumer:
    """Partitions with records; the assignment comes after the first poll."""

    def __init__(self, records: dict[TopicPartition, list[bytes]], batch: int = 2) -> None:
        self.records = records
        self.positions = dict.fromkeys(records, 0)
        self.batch = batch
        self.polls = 0

    def assignment(self) -> set[TopicPartition]:
        return set(self.records) if self.polls > 1 else set()

    async def getmany(
        self, *partitions: TopicPartition, timeout_ms: int = 0, max_records: int | None = None
    ) -> dict[TopicPartition, list[Any]]:
        self.polls += 1
        if self.polls == 1:
            return {}
        result = {}
        for tp, values in self.records.items():
            start = self.positions[tp]
            chunk = values[start : start + self.batch]
            if chunk:
                result[tp] = [SimpleNamespace(value=v) for v in chunk]
                self.positions[tp] += len(chunk)
        return result

    async def end_offsets(self, partitions: list[TopicPartition]) -> dict[TopicPartition, int]:
        return {tp: len(self.records[tp]) for tp in partitions}

    async def position(self, partition: TopicPartition) -> int:
        return self.positions[partition]


async def collect(consumer: Any, **kwargs: Any) -> list[bytes]:
    return [value async for value in projector_rebuild.read_until_caught_up(consumer, **kwargs)]


async def test_reader_stops_at_the_end_offsets() -> None:
    applications = TopicPartition("applications.events", 0)
    process = TopicPartition("process.events", 1)
    consumer = FakeKafkaConsumer(
        {applications: [b"a1", b"a2", b"a3"], process: [b"p1"], TopicPartition("x", 0): []}
    )
    values = await collect(consumer, poll_timeout_ms=0)
    assert sorted(values) == [b"a1", b"a2", b"a3", b"p1"]


async def test_reader_with_empty_topics_stops_at_once() -> None:
    consumer = FakeKafkaConsumer({TopicPartition("clients.events", 0): []})
    assert await collect(consumer, poll_timeout_ms=0) == []


async def test_reader_fails_without_partitions() -> None:
    consumer = FakeKafkaConsumer({})
    with pytest.raises(RuntimeError, match="No partitions"):
        await collect(consumer, poll_timeout_ms=0, assignment_timeout_s=0)


def test_rebuild_uses_a_fresh_consumer_group_per_run() -> None:
    moment = datetime(2026, 10, 22, 13, 5, 9, tzinfo=UTC)
    assert (
        projector_rebuild.rebuild_group_id(moment) == "projector.read-models.rebuild-20261022130509"
    )
    assert callable(projector_rebuild.main)
