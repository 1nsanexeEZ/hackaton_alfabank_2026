"""Reads for other modules (the facade): no access checks here, the caller is
trusted code (process, scoring, decision, projector, bff)."""

from uuid import UUID

from src.core.exceptions.exceptions import NotFoundError
from src.modules.applications.application.dto.applications import (
    ApplicationCardDTO,
    ApplicationSummaryDTO,
    CompletenessDTO,
    DocumentDTO,
    ScoringInputDTO,
)
from src.modules.applications.application.interfaces.repositories import ApplicationRepository
from src.modules.applications.application.interfaces.storage import DocumentStorage
from src.modules.applications.application.mappers.dto import (
    card,
    document_dto,
    scoring_input,
    summary_dto,
)
from src.modules.applications.application.use_cases.common import violations
from src.modules.applications.domain.statuses import ACTIVE_STATUSES
from src.modules.clients.facade import ClientsFacade

MAX_LIST = 500


class GetCardUseCase:
    def __init__(self, repository: ApplicationRepository) -> None:
        self._repository = repository

    async def execute(self, application_id: UUID) -> ApplicationCardDTO:
        return card(await self._repository.get(application_id))


class GetCompletenessUseCase:
    def __init__(self, repository: ApplicationRepository, clients: ClientsFacade) -> None:
        self._repository = repository
        self._clients = clients

    async def execute(self, application_id: UUID) -> CompletenessDTO:
        application = await self._repository.get(application_id)
        found = await violations(self._repository, self._clients, application)
        return CompletenessDTO(
            application_id=application.id,
            complete=not found,
            missing_fields=tuple(v.field for v in found if not v.field.startswith("documents.")),
            missing_documents=tuple(
                v.field.removeprefix("documents.")
                for v in found
                if v.field.startswith("documents.")
            ),
        )


class GetScoringInputUseCase:
    def __init__(self, repository: ApplicationRepository) -> None:
        self._repository = repository

    async def execute(self, application_id: UUID) -> ScoringInputDTO:
        return scoring_input(await self._repository.get(application_id))


class ListForOrganizationUseCase:
    def __init__(self, repository: ApplicationRepository) -> None:
        self._repository = repository

    async def execute(
        self, organization_id: UUID, active_only: bool = False
    ) -> list[ApplicationSummaryDTO]:
        statuses = [s.value for s in ACTIVE_STATUSES] if active_only else None
        applications = await self._repository.search(None, organization_id, statuses, MAX_LIST, 0)
        return [summary_dto(application) for application in applications]


class ListDocumentsUseCase:
    def __init__(self, repository: ApplicationRepository) -> None:
        self._repository = repository

    async def execute(self, application_id: UUID, document_type: str | None) -> list[DocumentDTO]:
        application = await self._repository.get(application_id)
        return [document_dto(d) for d in application.uploaded_documents(document_type)]


class ReadDocumentUseCase:
    def __init__(self, repository: ApplicationRepository, storage: DocumentStorage) -> None:
        self._repository = repository
        self._storage = storage

    async def execute(self, application_id: UUID, document_id: UUID) -> bytes:
        application = await self._repository.get(application_id)
        document = application.document(document_id)
        if not document.is_uploaded:
            raise NotFoundError("Document is not uploaded")
        return await self._storage.read(document.s3_key)
