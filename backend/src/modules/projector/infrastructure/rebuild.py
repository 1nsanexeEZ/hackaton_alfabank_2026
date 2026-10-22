"""Rebuild of the read models: clear the tables, then apply every event again
with the same projection as the live consumer.

The source of the events is up to the caller (scripts/projector_rebuild.py
reads Kafka from the beginning). The inbox is not used: tables are empty and
every step of the projection is idempotent, so an event met twice is harmless.
"""

import json
import logging
from collections.abc import AsyncIterable
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import src.core.messaging.contracts  # noqa: F401  registers every contract
from src.core.facades import FacadeRegistry
from src.core.messaging.contracts.base import IntegrationMessage, get_contract
from src.core.messaging.envelope import Envelope
from src.modules.projector.infrastructure.consumer import projector_for
from src.modules.projector.infrastructure.repositories import SqlAlchemyReadModelStore

logger = logging.getLogger(__name__)


@dataclass
class RebuildStats:
    applied: int = 0
    # Not an envelope or an unknown message type: the live consumer sends them to the DLQ.
    skipped: int = 0
    failed: int = 0


def parse(body: dict[str, Any] | bytes) -> tuple[Envelope, IntegrationMessage] | None:
    try:
        raw = body if isinstance(body, dict) else json.loads(body)
        envelope = Envelope.model_validate(raw)
        return envelope, get_contract(envelope.type).model_validate(envelope.payload)
    except (ValueError, LookupError, PydanticValidationError):
        return None


async def clear_read_models(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as session:
        await SqlAlchemyReadModelStore(session).clear()
        await session.commit()


async def apply_one(
    session_factory: async_sessionmaker[AsyncSession],
    facades: FacadeRegistry,
    envelope: Envelope,
    message: IntegrationMessage,
) -> None:
    async with session_factory() as session:
        await projector_for(session, facades).apply(envelope, message)
        await session.commit()


async def rebuild(
    session_factory: async_sessionmaker[AsyncSession],
    facades: FacadeRegistry,
    messages: AsyncIterable[dict[str, Any] | bytes],
    attempts: int = 3,
) -> RebuildStats:
    await clear_read_models(session_factory)
    stats = RebuildStats()
    async for body in messages:
        parsed = parse(body)
        if parsed is None:
            stats.skipped += 1
            continue
        envelope, message = parsed
        for attempt in range(1, attempts + 1):
            try:
                await apply_one(session_factory, facades, envelope, message)
            except Exception as exc:  # a concurrent live consumer may win a row: retry
                if attempt == attempts:
                    stats.failed += 1
                    logger.error(
                        "Rebuild could not apply %s %s: %r", envelope.type, envelope.event_id, exc
                    )
                continue
            stats.applied += 1
            break
    return stats
