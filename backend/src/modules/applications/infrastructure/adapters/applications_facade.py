"""ApplicationsFacade for other modules. Only calls the use cases, no logic of its own.
Built per session: reads join the caller's transaction."""

from uuid import UUID

from src.modules.applications.application.dto.applications import (
    ApplicationCardDTO,
    ApplicationSummaryDTO,
    CompletenessDTO,
    DocumentDTO,
    ScoringInputDTO,
)
from src.modules.applications.application.use_cases.cards import (
    GetCardUseCase,
    GetCompletenessUseCase,
    GetScoringInputUseCase,
    ListDocumentsUseCase,
    ListForOrganizationUseCase,
    ListSubmittedUseCase,
    ReadDocumentUseCase,
)
from src.modules.applications.facade import ApplicationsFacade


class ApplicationsFacadeImpl(ApplicationsFacade):
    def __init__(
        self,
        get_card: GetCardUseCase,
        get_completeness: GetCompletenessUseCase,
        get_scoring_input: GetScoringInputUseCase,
        list_for_organization: ListForOrganizationUseCase,
        list_documents: ListDocumentsUseCase,
        read_document: ReadDocumentUseCase,
        list_submitted: ListSubmittedUseCase,
    ) -> None:
        self._get_card = get_card
        self._get_completeness = get_completeness
        self._get_scoring_input = get_scoring_input
        self._list_for_organization = list_for_organization
        self._list_documents = list_documents
        self._read_document = read_document
        self._list_submitted = list_submitted

    async def get_card(self, application_id: UUID) -> ApplicationCardDTO:
        return await self._get_card.execute(application_id)

    async def get_completeness(self, application_id: UUID) -> CompletenessDTO:
        return await self._get_completeness.execute(application_id)

    async def get_scoring_input(self, application_id: UUID) -> ScoringInputDTO:
        return await self._get_scoring_input.execute(application_id)

    async def list_for_organization(
        self, organization_id: UUID, active_only: bool = False
    ) -> list[ApplicationSummaryDTO]:
        return await self._list_for_organization.execute(organization_id, active_only)

    async def list_submitted(self, limit: int) -> list[ApplicationSummaryDTO]:
        return await self._list_submitted.execute(limit)

    async def list_documents(
        self, application_id: UUID, document_type: str | None = None
    ) -> list[DocumentDTO]:
        return await self._list_documents.execute(application_id, document_type)

    async def read_document(self, application_id: UUID, document_id: UUID) -> bytes:
        return await self._read_document.execute(application_id, document_id)
