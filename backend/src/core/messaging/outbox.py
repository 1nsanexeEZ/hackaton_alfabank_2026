"""Transactional outbox: a message is stored in the same transaction as the
business change, a relay publishes it to Kafka later. So a change is never
committed without its message and a message never goes out without its change."""

from datetime import datetime
from typing import Any, Protocol
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, DateTime, Index, Integer, String, Text, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from src.core.domain.clock import Clock
from src.core.infrastructure.database.base import Base, JSONType
from src.core.messaging.contracts.base import IntegrationMessage
from src.core.messaging.envelope import Envelope


class OutboxRecord(Base):
    __tablename__ = "core_outbox"
    __table_args__ = (
        # The relay only looks at what is not published yet.
        Index(
            "ix_core_outbox_unpublished",
            "id",
            postgresql_where=text("published_at IS NULL"),
            sqlite_where=text("published_at IS NULL"),
        ),
    )

    # Monotonic id keeps the publishing order.
    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer(), "sqlite"), primary_key=True, autoincrement=True
    )
    event_id: Mapped[UUID] = mapped_column(unique=True)
    topic: Mapped[str] = mapped_column(String(255))
    key: Mapped[str] = mapped_column(String(255))
    message_type: Mapped[str] = mapped_column(String(128))
    envelope: Mapped[dict[str, Any]] = mapped_column(JSONType)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    attempts: Mapped[int] = mapped_column(default=0)
    last_error: Mapped[str | None] = mapped_column(Text, default=None)


class OutboxWriter(Protocol):
    async def add(
        self,
        message: IntegrationMessage,
        *,
        key: UUID | str,
        correlation_id: UUID,
        causation_id: UUID | None = None,
    ) -> UUID:
        """Stage a message in the current transaction, returns its event_id."""
        ...


def build_envelope(
    message: IntegrationMessage,
    *,
    producer: str,
    occurred_at: datetime,
    correlation_id: UUID,
    causation_id: UUID | None = None,
    event_id: UUID | None = None,
) -> Envelope:
    return Envelope(
        event_id=event_id or uuid4(),
        type=message.TYPE,
        schema_version=message.SCHEMA_VERSION,
        occurred_at=occurred_at,
        producer=producer,
        correlation_id=correlation_id,
        causation_id=causation_id,
        payload=message.model_dump(mode="json"),
    )


class SqlAlchemyOutboxWriter:
    def __init__(self, session: AsyncSession, producer: str, clock: Clock) -> None:
        self._session = session
        self._producer = producer
        self._clock = clock

    async def add(
        self,
        message: IntegrationMessage,
        *,
        key: UUID | str,
        correlation_id: UUID,
        causation_id: UUID | None = None,
    ) -> UUID:
        now = self._clock.now()
        envelope = build_envelope(
            message,
            producer=self._producer,
            occurred_at=now,
            correlation_id=correlation_id,
            causation_id=causation_id,
        )
        self._session.add(
            OutboxRecord(
                event_id=envelope.event_id,
                topic=message.TOPIC,
                key=str(key),
                message_type=message.TYPE,
                envelope=envelope.model_dump(mode="json"),
                created_at=now,
            )
        )
        return envelope.event_id
