from typing import Protocol
from uuid import UUID

from src.core.messaging.contracts.base import IntegrationMessage


class EventOutbox(Protocol):
    """The outbox of the current transaction (core SqlAlchemyOutboxWriter)."""

    async def add(
        self,
        message: IntegrationMessage,
        *,
        key: UUID | str,
        correlation_id: UUID,
        causation_id: UUID | None = None,
    ) -> UUID: ...
