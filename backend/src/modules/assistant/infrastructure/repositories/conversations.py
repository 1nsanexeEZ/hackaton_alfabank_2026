"""Conversations in `assistant_conversations` and `assistant_messages`."""

from collections.abc import Sequence
from typing import cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.assistant.application.interfaces.repositories import ConversationRepository
from src.modules.assistant.domain.conversation import Conversation, Mode, Role, StoredMessage
from src.modules.assistant.domain.exceptions import ConversationNotFoundError
from src.modules.assistant.infrastructure.database.models import (
    AssistantConversationRecord,
    AssistantMessageRecord,
)

# The history a conversation shows: the latest messages.
HISTORY_LIMIT = 200


class SqlAlchemyConversationRepository(ConversationRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, conversation: Conversation) -> None:
        self._session.add(
            AssistantConversationRecord(
                id=conversation.id,
                owner_id=conversation.owner_id,
                created_at=conversation.created_at,
            )
        )
        await self._session.flush()

    async def get(self, owner_id: UUID, conversation_id: UUID) -> Conversation:
        record = await self._session.scalar(
            select(AssistantConversationRecord).where(
                AssistantConversationRecord.id == conversation_id,
                AssistantConversationRecord.user_is_owner(owner_id),
            )
        )
        if record is None:
            raise ConversationNotFoundError()
        latest = (
            await self._session.scalars(
                select(AssistantMessageRecord)
                .where(AssistantMessageRecord.conversation_id == conversation_id)
                .order_by(AssistantMessageRecord.position.desc())
                .limit(HISTORY_LIMIT)
            )
        ).all()
        return Conversation(
            id=record.id,
            owner_id=record.owner_id,
            created_at=record.created_at,
            messages=tuple(_message(m) for m in reversed(latest)),
        )

    async def append(self, conversation_id: UUID, messages: Sequence[StoredMessage]) -> None:
        last = await self._session.scalar(
            select(func.max(AssistantMessageRecord.position)).where(
                AssistantMessageRecord.conversation_id == conversation_id
            )
        )
        position = 0 if last is None else last + 1
        for offset, message in enumerate(messages):
            self._session.add(
                AssistantMessageRecord(
                    id=message.id,
                    conversation_id=conversation_id,
                    position=position + offset,
                    role=message.role,
                    text=message.text,
                    created_at=message.created_at,
                    application_id=message.application_id,
                    intent=message.intent,
                    mode=message.mode,
                )
            )
        await self._session.flush()


def _message(record: AssistantMessageRecord) -> StoredMessage:
    return StoredMessage(
        id=record.id,
        role=cast(Role, record.role),
        text=record.text,
        created_at=record.created_at,
        application_id=record.application_id,
        intent=record.intent,
        mode=cast(Mode | None, record.mode),
    )
