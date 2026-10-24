"""SQLAlchemy models of support. Tables are prefixed with `support_`."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Sequence, String, Text
from sqlalchemy.orm import Mapped, declared_attr, mapped_column, relationship

from src.core.infrastructure.database.base import Base
from src.core.infrastructure.database.mixins import (
    OwnableMixin,
    UUIDPrimaryKeyMixin,
    VersionMixin,
)

# Numbers ТП-<year>-<NNNNNN>; on SQLite (tests) the repository counts rows instead.
NUMBER_SEQUENCE = Sequence("support_ticket_number_seq", metadata=Base.metadata)


class TicketRecord(UUIDPrimaryKeyMixin, OwnableMixin, VersionMixin, Base):
    """`owner_id` — the client who opened the ticket: the `own_only` policy."""

    __tablename__ = "support_tickets"
    __table_args__ = (
        # The staff queue: by status, newest activity first.
        Index("ix_support_tickets_status_updated_at", "status", "updated_at"),
    )

    @declared_attr.directive
    def __mapper_args__(cls) -> dict[str, Any]:
        # Optimistic locking: UPDATE ... WHERE version = :loaded. Of two employees
        # taking the ticket at once, the second one matches no row (409).
        return {"version_id_col": cls.__table__.c.version}

    number: Mapped[str] = mapped_column(String(32), unique=True)
    subject: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16))
    # No foreign keys: companies, applications and accounts live in other modules.
    organization_id: Mapped[UUID | None] = mapped_column(index=True)
    application_id: Mapped[UUID | None] = mapped_column(index=True)
    assignee_id: Mapped[UUID | None] = mapped_column(index=True)
    taken_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    messages: Mapped[list["MessageRecord"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="MessageRecord.position"
    )


class MessageRecord(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "support_messages"
    __table_args__ = (
        # Order of the chat; also a second guard against two writers of one ticket.
        Index("uq_support_messages_ticket_position", "ticket_id", "position", unique=True),
    )

    ticket_id: Mapped[UUID] = mapped_column(ForeignKey("support_tickets.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)
    author_id: Mapped[UUID]
    side: Mapped[str] = mapped_column(String(16))
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
