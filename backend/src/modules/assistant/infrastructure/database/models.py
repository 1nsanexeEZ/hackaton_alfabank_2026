"""SQLAlchemy models of the assistant. Tables are prefixed with `assistant_`."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.core.infrastructure.database.base import Base
from src.core.infrastructure.database.mixins import OwnableMixin, UUIDPrimaryKeyMixin


class AssistantConversationRecord(UUIDPrimaryKeyMixin, OwnableMixin, Base):
    """`owner_id` — the account that started the conversation: only it reads it."""

    __tablename__ = "assistant_conversations"

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AssistantMessageRecord(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "assistant_messages"
    __table_args__ = (
        Index(
            "uq_assistant_messages_conversation_position",
            "conversation_id",
            "position",
            unique=True,
        ),
    )

    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("assistant_conversations.id", ondelete="CASCADE")
    )
    position: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(16))
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # No foreign key: applications live in their own module.
    application_id: Mapped[UUID | None]
    intent: Mapped[str | None] = mapped_column(String(32))
    mode: Mapped[str | None] = mapped_column(String(16))
