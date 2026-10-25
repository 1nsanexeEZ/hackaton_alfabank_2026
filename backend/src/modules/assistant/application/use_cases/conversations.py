"""Conversations: each one is seen only by the account that started it."""

from uuid import UUID, uuid4

from src.core.domain.clock import Clock
from src.core.uow import UnitOfWork
from src.modules.assistant.application.dto.assistant import ApplicationRefDTO, ConversationDTO
from src.modules.assistant.application.interfaces.context import ContextSource
from src.modules.assistant.application.interfaces.repositories import ConversationRepository
from src.modules.assistant.domain.conversation import Conversation
from src.modules.assistant.domain.views import Viewer


class StartConversationUseCase:
    def __init__(self, uow: UnitOfWork, repository: ConversationRepository, clock: Clock) -> None:
        self._uow = uow
        self._repository = repository
        self._clock = clock

    async def execute(self, viewer: Viewer) -> ConversationDTO:
        conversation = Conversation(
            id=uuid4(), owner_id=viewer.account_id, created_at=self._clock.now()
        )
        async with self._uow:
            await self._repository.add(conversation)
            await self._uow.commit()
        return ConversationDTO.of(conversation)


class GetConversationUseCase:
    def __init__(self, repository: ConversationRepository) -> None:
        self._repository = repository

    async def execute(self, viewer: Viewer, conversation_id: UUID) -> ConversationDTO:
        return ConversationDTO.of(await self._repository.get(viewer.account_id, conversation_id))


class ListApplicationsUseCase:
    """The applications to pick one for the chat."""

    def __init__(self, source: ContextSource) -> None:
        self._source = source

    async def execute(self, viewer: Viewer) -> list[ApplicationRefDTO]:
        return [ApplicationRefDTO.of(a) for a in await self._source.list_applications(viewer)]
