from dataclasses import dataclass
from types import TracebackType
from typing import Self
from uuid import UUID, uuid4

from src.core.messaging.contracts.base import IntegrationMessage


@dataclass(frozen=True)
class StagedMessage:
    event_id: UUID
    message: IntegrationMessage
    key: str
    correlation_id: UUID
    causation_id: UUID | None


class FakeOutboxWriter:
    def __init__(self) -> None:
        self.messages: list[StagedMessage] = []

    async def add(
        self,
        message: IntegrationMessage,
        *,
        key: UUID | str,
        correlation_id: UUID,
        causation_id: UUID | None = None,
    ) -> UUID:
        event_id = uuid4()
        self.messages.append(
            StagedMessage(event_id, message, str(key), correlation_id, causation_id)
        )
        return event_id

    def of_type[M: IntegrationMessage](self, message_type: type[M]) -> list[M]:
        return [m.message for m in self.messages if isinstance(m.message, message_type)]  # type: ignore[misc]


class FakeInboxGuard:
    def __init__(self) -> None:
        self.processed: set[tuple[str, UUID]] = set()

    async def seen(self, consumer: str, event_id: UUID) -> bool:
        return (consumer, event_id) in self.processed

    async def mark(self, consumer: str, event_id: UUID) -> None:
        self.processed.add((consumer, event_id))


class FakeUnitOfWork:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.rollbacks += 1

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1
