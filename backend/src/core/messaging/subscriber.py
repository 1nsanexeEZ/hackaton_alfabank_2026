"""Consuming: modules declare Subscriptions, core takes care of parsing,
idempotency (inbox), transactions, retries and the dead letter queue.

A handler gets the parsed contract and a HandlerContext with its own session,
outbox writer and facades. It must not commit: the processor commits the
handler's changes, the outbox records and the inbox mark together.
"""

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol, TypeVar

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.domain.clock import Clock
from src.core.facades import FacadeRegistry
from src.core.messaging.contracts.base import IntegrationMessage, get_contract
from src.core.messaging.envelope import Envelope
from src.core.messaging.inbox import SqlAlchemyInboxGuard
from src.core.messaging.outbox import OutboxWriter, SqlAlchemyOutboxWriter

logger = logging.getLogger(__name__)

T = TypeVar("T")

Outcome = Literal["processed", "duplicate", "skipped", "dead_letter"]


@dataclass
class HandlerContext:
    envelope: Envelope
    session: AsyncSession
    outbox: OutboxWriter
    facades: FacadeRegistry
    clock: Clock

    def facade(self, key: type[T]) -> T:
        return self.facades.get(key, self.session)


Handler = Callable[[HandlerContext, Any], Awaitable[None]]


@dataclass(frozen=True)
class Subscription:
    """`module` is the producer name for messages the handler sends;
    `group_id` is the Kafka consumer group and the inbox consumer name.
    `message_types` filters the topic (None — every type)."""

    module: str
    topic: str
    group_id: str
    handler: Handler
    message_types: frozenset[str] | None = None


class DeadLetterPublisher(Protocol):
    async def publish_dead_letter(self, topic: str, body: dict[str, Any], error: str) -> None: ...


class MessageProcessor:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        facades: FacadeRegistry,
        clock: Clock,
        dead_letters: DeadLetterPublisher,
        backoff_seconds: Sequence[float] = (0.5, 1.0, 2.0),
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._session_factory = session_factory
        self._facades = facades
        self._clock = clock
        self._dead_letters = dead_letters
        self._backoff = tuple(backoff_seconds)
        self._sleep = sleep

    async def process(self, subscription: Subscription, body: dict[str, Any] | bytes) -> Outcome:
        raw = _as_dict(body)
        try:
            envelope = Envelope.model_validate(raw)
        except PydanticValidationError as exc:
            return await self._dead_letter(subscription, raw, f"invalid envelope: {exc}")

        if (
            subscription.message_types is not None
            and envelope.type not in subscription.message_types
        ):
            return "skipped"

        try:
            payload = get_contract(envelope.type).model_validate(envelope.payload)
        except (LookupError, PydanticValidationError) as exc:
            return await self._dead_letter(subscription, raw, f"invalid payload: {exc}")

        attempts = len(self._backoff) or 1
        last_error: Exception | None = None
        for attempt in range(attempts):
            try:
                return await self._handle_once(subscription, envelope, payload)
            except Exception as exc:  # retried, then dead-lettered
                last_error = exc
                logger.warning(
                    "Handler %s failed on %s %s (attempt %s/%s): %s",
                    subscription.group_id,
                    envelope.type,
                    envelope.event_id,
                    attempt + 1,
                    attempts,
                    exc,
                )
                if attempt < attempts - 1:
                    await self._sleep(self._backoff[attempt])
        return await self._dead_letter(subscription, raw, repr(last_error))

    async def _handle_once(
        self, subscription: Subscription, envelope: Envelope, payload: IntegrationMessage
    ) -> Outcome:
        async with self._session_factory() as session:
            inbox = SqlAlchemyInboxGuard(session, self._clock)
            if await inbox.seen(subscription.group_id, envelope.event_id):
                return "duplicate"
            context = HandlerContext(
                envelope=envelope,
                session=session,
                outbox=SqlAlchemyOutboxWriter(session, subscription.module, self._clock),
                facades=self._facades,
                clock=self._clock,
            )
            await subscription.handler(context, payload)
            await inbox.mark(subscription.group_id, envelope.event_id)
            await session.commit()
        return "processed"

    async def _dead_letter(
        self, subscription: Subscription, raw: dict[str, Any], error: str
    ) -> Outcome:
        logger.error("Message to %s goes to the dead letter queue: %s", subscription.topic, error)
        await self._dead_letters.publish_dead_letter(subscription.topic, raw, error[:1000])
        return "dead_letter"


def _as_dict(body: dict[str, Any] | bytes) -> dict[str, Any]:
    if isinstance(body, dict):
        return body
    try:
        decoded = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return {"raw": body.decode("utf-8", errors="replace")}
    return decoded if isinstance(decoded, dict) else {"raw": decoded}
