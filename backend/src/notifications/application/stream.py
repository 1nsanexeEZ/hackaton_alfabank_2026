"""Live feed over SSE.

EventSource can't send an Authorization header, so the client exchanges its
token for a one-time ticket (POST /feed/stream-ticket) and opens
GET /feed/stream?ticket=. New records are found by polling the database for
records after the last delivered position: it works the same with several
backend instances and needs no in-memory bus."""

import asyncio
import hashlib
import secrets
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID

from src.core.domain.clock import Clock
from src.core.exceptions.exceptions import UnauthorizedError
from src.core.uow import UnitOfWork
from src.notifications.application.ports import FeedRecord, FeedStore, StreamGrant, TicketStore
from src.notifications.domain.feed import Recipient

TICKET_TTL_SECONDS = 30
POLL_INTERVAL_SECONDS = 1.0
HEARTBEAT_SECONDS = 15.0
# The stream closes after this time: the client takes a new ticket (the token
# may have expired meanwhile) and reconnects with last_event_id.
MAX_STREAM_SECONDS = 600.0
BATCH_SIZE = 50

# Records that change the application card: the client refreshes it.
APPLICATION_ITEM_TYPES = frozenset(
    {"status_changed", "stage_changed", "info_requested", "offer_ready"}
)

StreamEventName = Literal["feed_item", "application_updated", "heartbeat"]


def ticket_hash(ticket: str) -> str:
    return hashlib.sha256(ticket.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class IssuedTicket:
    ticket: str
    expires_at: datetime


class StreamTickets:
    def __init__(self, store: TicketStore, uow: UnitOfWork, clock: Clock) -> None:
        self._store = store
        self._uow = uow
        self._clock = clock

    async def issue(self, account_id: UUID, roles: Sequence[str]) -> IssuedTicket:
        now = self._clock.now()
        ticket = secrets.token_urlsafe(32)
        expires_at = now + timedelta(seconds=TICKET_TTL_SECONDS)
        async with self._uow:
            await self._store.add(ticket_hash(ticket), account_id, list(roles), expires_at, now)
            await self._uow.commit()
        return IssuedTicket(ticket, expires_at)

    async def redeem(self, ticket: str) -> StreamGrant:
        async with self._uow:
            grant = await self._store.redeem(ticket_hash(ticket), self._clock.now())
            if grant is None:
                raise UnauthorizedError("Stream ticket is invalid, used or expired")
            await self._uow.commit()
        return grant


@dataclass(frozen=True, slots=True)
class StreamEvent:
    event: StreamEventName
    id: str | None = None
    record: FeedRecord | None = None
    at: datetime | None = None


# Every poll opens its own short session: a stream must not hold a connection.
FeedStoreFactory = Callable[[], AbstractAsyncContextManager[FeedStore]]


def parse_last_event_id(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        position = int(value.strip())
    except ValueError:
        return None
    return position if position >= 0 else None


async def feed_events(
    open_store: FeedStoreFactory,
    recipients: Sequence[Recipient],
    last_event_id: int | None,
    clock: Clock,
    *,
    poll_seconds: float,
    heartbeat_seconds: float,
    max_seconds: float,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> AsyncIterator[StreamEvent]:
    """`feed_item` for every new or replaced record (id = its stream position),
    `application_updated` after a record that changes an application,
    `heartbeat` when nothing happened for `heartbeat_seconds`.
    Without last_event_id the stream starts from now."""
    if last_event_id is None:
        async with open_store() as store:
            cursor = await store.latest_seq(recipients)
    else:
        cursor = last_event_id
    started = last_sent = monotonic()
    while monotonic() - started < max_seconds:
        async with open_store() as store:
            records = await store.after(recipients, cursor, BATCH_SIZE)
        for record in records:
            cursor = record.seq
            yield StreamEvent("feed_item", id=str(record.seq), record=record)
            if record.item.application_id and record.item.type in APPLICATION_ITEM_TYPES:
                yield StreamEvent("application_updated", id=str(record.seq), record=record)
        if records:
            last_sent = monotonic()
        elif monotonic() - last_sent >= heartbeat_seconds:
            yield StreamEvent("heartbeat", at=clock.now())
            last_sent = monotonic()
        if len(records) < BATCH_SIZE:
            await sleep(poll_seconds)
