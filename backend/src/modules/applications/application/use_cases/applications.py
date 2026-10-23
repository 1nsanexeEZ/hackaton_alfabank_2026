"""Reads of the applications API: the application, the list, what is missing."""

from collections.abc import Sequence
from uuid import UUID

from src.core.access.access_context import AccessContext
from src.modules.applications.application.dto.applications import ApplicationSummaryDTO
from src.modules.applications.application.dto.views import (
    ApplicationViewDTO,
    CompletenessReportDTO,
)
from src.modules.applications.application.interfaces.repositories import ApplicationRepository
from src.modules.applications.application.mappers.dto import summary_dto
from src.modules.applications.application.use_cases.common import view, violations
from src.modules.clients.facade import ClientsFacade


class GetApplicationUseCase:
    def __init__(self, repository: ApplicationRepository, clients: ClientsFacade) -> None:
        self._repository = repository
        self._clients = clients

    async def execute(self, access: AccessContext, application_id: UUID) -> ApplicationViewDTO:
        application = await self._repository.get(application_id, access)
        return await view(self._clients, access, application)


class ListApplicationsUseCase:
    def __init__(self, repository: ApplicationRepository) -> None:
        self._repository = repository

    async def execute(
        self,
        access: AccessContext,
        organization_id: UUID | None,
        statuses: Sequence[str] | None,
        limit: int,
        offset: int,
    ) -> list[ApplicationSummaryDTO]:
        applications = await self._repository.search(
            access, organization_id, statuses, limit, offset
        )
        return [summary_dto(application) for application in applications]


class CheckCompletenessUseCase:
    def __init__(self, repository: ApplicationRepository, clients: ClientsFacade) -> None:
        self._repository = repository
        self._clients = clients

    async def execute(self, access: AccessContext, application_id: UUID) -> CompletenessReportDTO:
        application = await self._repository.get(application_id, access)
        found = await violations(self._repository, self._clients, application)
        return CompletenessReportDTO(
            complete=not found, violations=tuple(v.as_dict() for v in found)
        )
