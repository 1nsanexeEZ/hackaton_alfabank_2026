"""Inbox: Kafka delivers at least once, so every consumer remembers processed
event ids in the same transaction as its own changes."""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy import DateTime, String, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from src.core.domain.clock import Clock
from src.core.infrastructure.database.base import Base


class InboxRecord(Base):
    __tablename__ = "core_inbox"

    consumer: Mapped[str] = mapped_column(String(128), primary_key=True)
    event_id: Mapped[UUID] = mapped_column(primary_key=True)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class InboxGuard(Protocol):
    async def seen(self, consumer: str, event_id: UUID) -> bool: ...

    async def mark(self, consumer: str, event_id: UUID) -> None: ...


class SqlAlchemyInboxGuard:
    def __init__(self, session: AsyncSession, clock: Clock) -> None:
        self._session = session
        self._clock = clock

    async def seen(self, consumer: str, event_id: UUID) -> bool:
        stmt = select(InboxRecord.event_id).where(
            InboxRecord.consumer == consumer, InboxRecord.event_id == event_id
        )
        return (await self._session.execute(stmt)).first() is not None

    async def mark(self, consumer: str, event_id: UUID) -> None:
        self._session.add(
            InboxRecord(consumer=consumer, event_id=event_id, processed_at=self._clock.now())
        )
