"""SSE: one-time tickets and the event generator (tested directly, without an
endless HTTP stream)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.domain.clock import FrozenClock
from src.core.exceptions.exceptions import UnauthorizedError
from src.core.uow import SqlAlchemyUnitOfWork
from src.modules.notifications.application.dto.stream import StreamEvent
from src.modules.notifications.application.interfaces.repositories import FeedStore
from src.modules.notifications.application.use_cases.stream import (
    IssueStreamTicketUseCase,
    RedeemStreamTicketUseCase,
    StreamFeedUseCase,
    parse_last_event_id,
)
from src.modules.notifications.domain.feed import UNDERWRITERS, Delivery, FeedEntry, Recipient
from src.modules.notifications.infrastructure.repositories.feed import SqlAlchemyFeedStore
from src.modules.notifications.infrastructure.repositories.tickets import SqlAlchemyTicketStore

ACCOUNT = uuid4()
ME = (Recipient.account(ACCOUNT),)


def entry(title: str, application_id: UUID | None = None) -> FeedEntry:
    return FeedEntry(
        type="status_changed",
        audience="client",
        title=title,
        body="",
        application_id=application_id,
    )


class Feed:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession], clock: FrozenClock):
        self.session_factory = session_factory
        self.clock = clock

    @asynccontextmanager
    async def open_store(self) -> AsyncIterator[FeedStore]:
        async with self.session_factory() as session:
            yield SqlAlchemyFeedStore(session)

    async def add(self, title: str, recipients=ME, application_id: UUID | None = None) -> None:
        async with self.session_factory() as session:
            await SqlAlchemyFeedStore(session).append(
                Delivery(entry(title, application_id), tuple(recipients)),
                uuid4(),
                "Test",
                self.clock.now(),
            )
            await session.commit()

    def events(self, last_event_id: int | None, **options) -> AsyncIterator[StreamEvent]:
        defaults = {"poll_seconds": 0.0, "heartbeat_seconds": 1000.0, "max_seconds": 1000.0}
        stream = StreamFeedUseCase(self.open_store, self.clock, **(defaults | options))
        return stream.execute(ME, last_event_id)


@pytest.fixture
def clock() -> FrozenClock:
    return FrozenClock()


@pytest.fixture
def feed(session_factory: async_sessionmaker[AsyncSession], clock: FrozenClock) -> Feed:
    return Feed(session_factory, clock)


async def test_stream_delivers_a_record_created_after_connect(feed: Feed) -> None:
    await feed.add("было до подключения")
    added: list[str] = []
    application_id = uuid4()

    async def sleep(_: float) -> None:
        # the first poll found nothing new: a record appears while the client waits
        if not added:
            added.append("x")
            await feed.add("новая запись", application_id=application_id)

    events = feed.events(None, sleep=sleep)
    first = await anext(events)
    second = await anext(events)
    await events.aclose()

    assert first.event == "feed_item" and first.record is not None
    assert first.record.item.title == "новая запись"
    assert first.id == str(first.record.seq)
    assert second.event == "application_updated" and second.id == first.id


async def test_last_event_id_replays_what_was_missed(feed: Feed) -> None:
    await feed.add("первая")
    await feed.add("вторая")
    await feed.add("чужая", recipients=(Recipient.account(uuid4()),))
    events = feed.events(0, max_seconds=0.05)
    received = [e async for e in events]
    assert [e.record.item.title for e in received if e.record] == ["первая", "вторая"]
    ids = [int(e.id) for e in received if e.id]
    assert ids == sorted(ids)

    after_first = [e async for e in feed.events(ids[0], max_seconds=0.05)]
    assert [e.record.item.title for e in after_first if e.record] == ["вторая"]


async def test_role_records_reach_bank_staff(feed: Feed) -> None:
    await feed.add("задача", recipients=(UNDERWRITERS,))
    events = StreamFeedUseCase(
        feed.open_store,
        feed.clock,
        poll_seconds=0,
        heartbeat_seconds=1000,
        max_seconds=0.05,
    ).execute((*ME, UNDERWRITERS), 0)
    assert [e.record.item.title async for e in events if e.record] == ["задача"]


async def test_heartbeat_when_nothing_happens(feed: Feed) -> None:
    ticks = iter(range(100))
    events = feed.events(None, heartbeat_seconds=1, monotonic=lambda: float(next(ticks)))
    event = await anext(events)
    await events.aclose()
    assert event.event == "heartbeat" and event.id is None
    assert event.at == feed.clock.now()


async def test_stream_closes_after_its_lifetime(feed: Feed) -> None:
    assert [e async for e in feed.events(None, max_seconds=0)] == []


@pytest.mark.parametrize(
    "value,expected", [("12", 12), (" 7 ", 7), ("abc", None), ("-1", None), (None, None)]
)
def test_last_event_id_parsing(value: str | None, expected: int | None) -> None:
    assert parse_last_event_id(value) == expected


# --- tickets -----------------------------------------------------------------


def issue_ticket(session: AsyncSession, clock: FrozenClock) -> IssueStreamTicketUseCase:
    return IssueStreamTicketUseCase(
        SqlAlchemyTicketStore(session), SqlAlchemyUnitOfWork(session), clock
    )


def redeem_ticket(session: AsyncSession, clock: FrozenClock) -> RedeemStreamTicketUseCase:
    return RedeemStreamTicketUseCase(
        SqlAlchemyTicketStore(session), SqlAlchemyUnitOfWork(session), clock
    )


async def test_ticket_is_one_time(
    session_factory: async_sessionmaker[AsyncSession], clock: FrozenClock
) -> None:
    async with session_factory() as session:
        issued = await issue_ticket(session, clock).execute(ACCOUNT, ["underwriter"])
    assert issued.expires_at == clock.now() + timedelta(seconds=30)

    async with session_factory() as session:
        grant = await redeem_ticket(session, clock).execute(issued.ticket)
    assert grant.account_id == ACCOUNT
    assert grant.recipients == (Recipient.account(ACCOUNT), UNDERWRITERS)

    async with session_factory() as session:
        with pytest.raises(UnauthorizedError):
            await redeem_ticket(session, clock).execute(issued.ticket)


async def test_expired_or_unknown_ticket_is_refused(
    session_factory: async_sessionmaker[AsyncSession], clock: FrozenClock
) -> None:
    async with session_factory() as session:
        issued = await issue_ticket(session, clock).execute(ACCOUNT, [])
    clock.advance(timedelta(seconds=31))
    for ticket in (issued.ticket, "no-such-ticket"):
        async with session_factory() as session:
            with pytest.raises(UnauthorizedError):
                await redeem_ticket(session, clock).execute(ticket)


async def test_ticket_is_stored_hashed(
    session_factory: async_sessionmaker[AsyncSession], clock: FrozenClock
) -> None:
    from sqlalchemy import select

    from src.modules.notifications.infrastructure.database.models import StreamTicket

    async with session_factory() as session:
        issued = await issue_ticket(session, clock).execute(ACCOUNT, [])
        row = (await session.scalars(select(StreamTicket))).one()
    assert row.ticket_hash != issued.ticket and len(row.ticket_hash) == 64
