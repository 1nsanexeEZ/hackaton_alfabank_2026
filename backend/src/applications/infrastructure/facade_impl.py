from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.applications.application.ports import DocumentStorage
from src.applications.application.translate import card, document_dto, scoring_input, summary_dto
from src.applications.domain.statuses import ACTIVE_STATUSES
from src.applications.facade import (
    ApplicationCardDTO,
    ApplicationSummaryDTO,
    CompletenessDTO,
    DocumentDTO,
    ScoringInputDTO,
)
from src.applications.infrastructure.repository import SqlAlchemyApplicationRepository
from src.clients.facade import ClientsFacade
from src.core.exceptions.exceptions import NotFoundError
from src.core.facades import FacadeRegistry

MAX_LIST = 500


class ApplicationsFacadeImpl:
    """Read side for other modules: no access checks here, the caller is
    trusted code (process, scoring, decision, projector, bff)."""

    def __init__(
        self, session: AsyncSession, storage: DocumentStorage, facades: FacadeRegistry
    ) -> None:
        self._session = session
        self._repository = SqlAlchemyApplicationRepository(session)
        self._storage = storage
        self._facades = facades

    async def get_card(self, application_id: UUID) -> ApplicationCardDTO:
        return card(await self._repository.get(application_id))

    async def get_completeness(self, application_id: UUID) -> CompletenessDTO:
        application = await self._repository.get(application_id)
        if application.org_snapshot is not None:
            legal_form = application.org_snapshot.legal_form
        else:
            clients = self._facades.get(ClientsFacade, self._session)
            legal_form = (await clients.get_snapshot(application.organization_id)).legal_form
        other = await self._repository.find_active(
            application.organization_id, application.product_code, exclude_id=application.id
        )
        violations = application.check_ready(legal_form, has_other_active=other is not None)
        return CompletenessDTO(
            application_id=application.id,
            complete=not violations,
            missing_fields=tuple(
                v.field for v in violations if not v.field.startswith("documents.")
            ),
            missing_documents=tuple(
                v.field.removeprefix("documents.")
                for v in violations
                if v.field.startswith("documents.")
            ),
        )

    async def get_scoring_input(self, application_id: UUID) -> ScoringInputDTO:
        return scoring_input(await self._repository.get(application_id))

    async def list_for_organization(
        self, organization_id: UUID, active_only: bool = False
    ) -> list[ApplicationSummaryDTO]:
        statuses = [s.value for s in ACTIVE_STATUSES] if active_only else None
        applications = await self._repository.search(None, organization_id, statuses, MAX_LIST, 0)
        return [summary_dto(application) for application in applications]

    async def list_documents(
        self, application_id: UUID, document_type: str | None = None
    ) -> list[DocumentDTO]:
        application = await self._repository.get(application_id)
        return [document_dto(d) for d in application.uploaded_documents(document_type)]

    async def read_document(self, application_id: UUID, document_id: UUID) -> bytes:
        application = await self._repository.get(application_id)
        document = application.document(document_id)
        if not document.is_uploaded:
            raise NotFoundError("Document is not uploaded")
        return await self._storage.read(document.s3_key)
