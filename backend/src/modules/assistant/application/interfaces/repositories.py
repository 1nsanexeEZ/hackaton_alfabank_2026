from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from src.modules.assistant.domain.conversation import Conversation, StoredMessage


class ConversationRepository(Protocol):
    async def add(self, conversation: Conversation) -> None: ...

    async def get(self, owner_id: UUID, conversation_id: UUID) -> Conversation:
        """With the latest messages, oldest first. Raises ConversationNotFoundError:
        no such conversation or someone else's."""
        ...

    async def append(self, conversation_id: UUID, messages: Sequence[StoredMessage]) -> None: ...
