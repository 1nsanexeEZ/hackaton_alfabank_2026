"""Rebuild of the read models: clear the tables, then apply every event again
with the same projection as the live consumer.

The source of the events is up to the caller (scripts/projector_rebuild.py
reads Kafka from the beginning). The inbox is not used: tables are empty and
every step of the projection is idempotent, so an event met twice is harmless.
Every step runs in a transaction of its own.
"""

import logging
from collections.abc import AsyncIterable

from src.core.messaging.contracts.base import IntegrationMessage
from src.core.messaging.envelope import Envelope
from src.modules.projector.application.dto.rebuild import RebuildStats
from src.modules.projector.application.interfaces.transactions import ProjectionTransactions
from src.modules.projector.application.use_cases.project_event import ProjectEventUseCase

logger = logging.getLogger(__name__)

# None — not an envelope or an unknown message type: the rebuild skips it.
Event = tuple[Envelope, IntegrationMessage] | None


class ClearReadModelsUseCase:
    def __init__(self, transactions: ProjectionTransactions) -> None:
        self._transactions = transactions

    async def execute(self) -> None:
        async with self._transactions() as transaction:
            await transaction.store.clear()
            await transaction.commit()


class ReplayEventUseCase:
    """One event through the projection, in a transaction of its own and without the inbox."""

    def __init__(self, transactions: ProjectionTransactions) -> None:
        self._transactions = transactions

    async def execute(self, envelope: Envelope, message: IntegrationMessage) -> None:
        async with self._transactions() as transaction:
            projection = ProjectEventUseCase(transaction.store, transaction.facades)
            await projection.execute(envelope, message)
            await transaction.commit()


class RebuildReadModelsUseCase:
    def __init__(
        self, clear: ClearReadModelsUseCase, replay: ReplayEventUseCase, attempts: int = 3
    ) -> None:
        self._clear = clear
        self._replay = replay
        self._attempts = attempts

    async def execute(self, events: AsyncIterable[Event]) -> RebuildStats:
        await self._clear.execute()
        applied = skipped = failed = 0
        async for event in events:
            if event is None:
                skipped += 1
                continue
            envelope, message = event
            for attempt in range(1, self._attempts + 1):
                try:
                    await self._replay.execute(envelope, message)
                except Exception as exc:  # a concurrent live consumer may win a row: retry
                    if attempt == self._attempts:
                        failed += 1
                        logger.error(
                            "Rebuild could not apply %s %s: %r",
                            envelope.type,
                            envelope.event_id,
                            exc,
                        )
                    continue
                applied += 1
                break
        return RebuildStats(applied=applied, skipped=skipped, failed=failed)
