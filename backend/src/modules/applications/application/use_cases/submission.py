"""The client sends the application, answers the bank's questions or withdraws it."""

from uuid import UUID

from src.core.access.access_context import AccessContext
from src.core.domain.clock import Clock
from src.core.uow import UnitOfWork
from src.modules.applications.application.dto.views import ApplicationViewDTO
from src.modules.applications.application.interfaces.outbox import MessageOutbox
from src.modules.applications.application.interfaces.repositories import ApplicationRepository
from src.modules.applications.application.mappers.dto import snapshot_from_dto
from src.modules.applications.application.use_cases.common import (
    get_writable,
    save,
    take_profile_consents,
    view,
)
from src.modules.applications.domain.value_objects import Actor
from src.modules.clients.facade import ClientsFacade, OrgPermission
from src.modules.identity.facade import IdentityFacade


class SubmitApplicationUseCase:
    """The company data is frozen in the application at this moment; so are the consents,
    those the draft lacks are taken from the profile first."""

    def __init__(
        self,
        uow: UnitOfWork,
        repository: ApplicationRepository,
        outbox: MessageOutbox,
        clients: ClientsFacade,
        identity: IdentityFacade,
        clock: Clock,
    ) -> None:
        self._uow = uow
        self._repository = repository
        self._outbox = outbox
        self._clients = clients
        self._identity = identity
        self._clock = clock

    async def execute(self, access: AccessContext, application_id: UUID) -> ApplicationViewDTO:
        application = await get_writable(
            self._repository,
            self._clients,
            access,
            application_id,
            OrgPermission.SUBMIT_APPLICATION,
        )
        now = self._clock.now()
        await take_profile_consents(self._identity, application, access.user_id, now)
        snapshot = await self._clients.get_snapshot(application.organization_id)
        other = await self._repository.find_active(
            application.organization_id, application.product_code, exclude_id=application.id
        )
        application.submit(
            snapshot_from_dto(snapshot, now),
            actor=Actor.client(access.user_id),
            has_other_active=other is not None,
            now=now,
        )
        await save(self._uow, self._repository, self._outbox, application)
        return await view(self._clients, access, application)


class AnswerInfoRequestUseCase:
    def __init__(
        self,
        uow: UnitOfWork,
        repository: ApplicationRepository,
        outbox: MessageOutbox,
        clients: ClientsFacade,
        clock: Clock,
    ) -> None:
        self._uow = uow
        self._repository = repository
        self._outbox = outbox
        self._clients = clients
        self._clock = clock

    async def execute(
        self, access: AccessContext, application_id: UUID, info_request_id: UUID
    ) -> ApplicationViewDTO:
        application = await get_writable(
            self._repository,
            self._clients,
            access,
            application_id,
            OrgPermission.SUBMIT_APPLICATION,
        )
        application.answer_info_request(
            info_request_id, Actor.client(access.user_id), self._clock.now()
        )
        await save(self._uow, self._repository, self._outbox, application)
        return await view(self._clients, access, application)


class CancelApplicationUseCase:
    def __init__(
        self,
        uow: UnitOfWork,
        repository: ApplicationRepository,
        outbox: MessageOutbox,
        clients: ClientsFacade,
        clock: Clock,
    ) -> None:
        self._uow = uow
        self._repository = repository
        self._outbox = outbox
        self._clients = clients
        self._clock = clock

    async def execute(
        self, access: AccessContext, application_id: UUID, reason: str | None
    ) -> ApplicationViewDTO:
        application = await get_writable(
            self._repository,
            self._clients,
            access,
            application_id,
            OrgPermission.SUBMIT_APPLICATION,
        )
        application.cancel(Actor.client(access.user_id), self._clock.now(), reason)
        await save(self._uow, self._repository, self._outbox, application)
        return await view(self._clients, access, application)
