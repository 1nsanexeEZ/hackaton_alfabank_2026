"""SQLAlchemy models of notifications. Tables are prefixed with `notifications_`."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.core.infrastructure.database.base import Base, JSONType


class FeedItem(Base):
    """A feed record of one recipient: an account (`account`, id of the
    account) or a bank role (`role`, e.g. `underwriter`)."""

    __tablename__ = "notifications_feed_items"
    __table_args__ = (
        # One event gives a recipient at most one record: a redelivered event adds nothing.
        UniqueConstraint("source_event_id", "recipient_type", "recipient_id"),
        Index("ix_notifications_feed_items_recipient", "recipient_type", "recipient_id", "seq"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    # Position in the stream (SSE event id): new and replaced records get the next value.
    seq: Mapped[int] = mapped_column(BigInteger().with_variant(Integer(), "sqlite"), unique=True)
    source_event_id: Mapped[UUID]
    source_type: Mapped[str] = mapped_column(String(64))
    recipient_type: Mapped[str] = mapped_column(String(16))
    recipient_id: Mapped[str] = mapped_column(String(64))
    audience: Mapped[str] = mapped_column(String(16))
    type: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(String(512), default=None)
    priority: Mapped[str] = mapped_column(String(16))
    action_required: Mapped[bool] = mapped_column(Boolean, default=False)
    organization_id: Mapped[UUID | None] = mapped_column(index=True, default=None)
    application_id: Mapped[UUID | None] = mapped_column(index=True, default=None)
    # Records with the same key replace each other (stage of an application, a task).
    group_key: Mapped[str | None] = mapped_column(String(128), index=True, default=None)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class NewsItem(Base):
    """A news article with relevance tags; seeded by a stable slug."""

    __tablename__ = "notifications_news_items"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    slug: Mapped[str] = mapped_column(String(100), unique=True)
    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    okved_prefixes: Mapped[list[str]] = mapped_column(JSONType, default=list)
    product_codes: Mapped[list[str]] = mapped_column(JSONType, default=list)
    legal_forms: Mapped[list[str]] = mapped_column(JSONType, default=list)
    is_general: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class NewsRead(Base):
    __tablename__ = "notifications_news_reads"

    news_id: Mapped[UUID] = mapped_column(
        ForeignKey("notifications_news_items.id", ondelete="CASCADE"), primary_key=True
    )
    account_id: Mapped[UUID] = mapped_column(primary_key=True)
    read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class StreamTicket(Base):
    """One-time ticket for the SSE stream: EventSource can't send headers, so
    the token is exchanged for a short ticket in the query string. Kept in the
    database, not in memory: the stream may land on another backend instance."""

    __tablename__ = "notifications_stream_tickets"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    # sha256 of the ticket: the ticket itself is never stored.
    ticket_hash: Mapped[str] = mapped_column(String(64), unique=True)
    account_id: Mapped[UUID]
    # Bank roles whose feed the stream also carries.
    roles: Mapped[list[str]] = mapped_column(JSONType, default=list)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
