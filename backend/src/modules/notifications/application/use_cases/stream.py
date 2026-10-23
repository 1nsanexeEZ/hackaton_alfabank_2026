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
from datetime import timedelta
from uuid import UUID

from src.core.domain.clock import Clock
from src.core.exceptions.exceptions import UnauthorizedError
from src.core.uow import UnitOfWork
from src.modules.notifications.application.dto.stream import IssuedTicket, StreamEvent
from src.modules.notifications.application.interfaces.repositories import (
    FeedStoreFactory,
    TicketStore,
)
from src.modules.notifications.application.mappers.feed import feed_record_dto
from src.modules.notifications.domain.feed import Recipient
from src.modules.notifications.domain.viewers import StreamGrant

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


def ticket_hash(ticket: str) -> str:
    return hashlib.sha256(ticket.encode()).hexdigest()


def parse_last_event_id(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        position = int(value.strip())
    except ValueError:
        return None
    return position if position >= 0 else None


class IssueStreamTicketUseCase:
    def __init__(self, store: TicketStore, uow: UnitOfWork, clock: Clock) -> None:
        self._store = store
        self._uow = uow
        self._clock = clock

    async def execute(self, account_id: UUID, roles: Sequence[str]) -> IssuedTicket:
        now = self._clock.now()
        ticket = secrets.token_urlsafe(32)
        expires_at = now + timedelta(seconds=TICKET_TTL_SECONDS)
        async with self._uow:
            await self._store.add(ticket_hash(ticket), account_id, list(roles), expires_at, now)
            await self._uow.commit()
        return IssuedTicket(ticket, expires_at)


class RedeemStreamTicketUseCase:
    def __init__(self, store: TicketStore, uow: UnitOfWork, clock: Clock) -> None:
        self._store = store
        self._uow = uow
        self._clock = clock

    async def execute(self, ticket: str) -> StreamGrant:
        async with self._uow:
            grant = await self._store.redeem(ticket_hash(ticket), self._clock.now())
            if grant is None:
                raise UnauthorizedError("Stream ticket is invalid, used or expired")
            await self._uow.commit()
        return grant


class StreamFeedUseCase:
    def __init__(
        self,
        open_store: FeedStoreFactory,
        clock: Clock,
        *,
        poll_seconds: float,
        heartbeat_seconds: float,
        max_seconds: float,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._open_store = open_store
        self._clock = clock
        self._poll_seconds = poll_seconds
        self._heartbeat_seconds = heartbeat_seconds
        self._max_seconds = max_seconds
        self._sleep = sleep
        self._monotonic = monotonic

    async def execute(
        self, recipients: Sequence[Recipient], last_event_id: int | None
    ) -> AsyncIterator[StreamEvent]:
        """`feed_item` for every new or replaced record (id = its stream position),
        `application_updated` after a record that changes an application,
        `heartbeat` when nothing happened for `heartbeat_seconds`.
        Without last_event_id the stream starts from now."""
        if last_event_id is None:
            async with self._open_store() as store:
                cursor = await store.latest_seq(recipients)
        else:
            cursor = last_event_id
        started = last_sent = self._monotonic()
        while self._monotonic() - started < self._max_seconds:
            async with self._open_store() as store:
                records = [
                    feed_record_dto(r) for r in await store.after(recipients, cursor, BATCH_SIZE)
                ]
            for record in records:
                cursor = record.seq
                yield StreamEvent("feed_item", id=str(record.seq), record=record)
                if record.item.application_id and record.item.type in APPLICATION_ITEM_TYPES:
                    yield StreamEvent("application_updated", id=str(record.seq), record=record)
            if records:
                last_sent = self._monotonic()
            elif self._monotonic() - last_sent >= self._heartbeat_seconds:
                yield StreamEvent("heartbeat", at=self._clock.now())
                last_sent = self._monotonic()
            if len(records) < BATCH_SIZE:
                await self._sleep(self._poll_seconds)
