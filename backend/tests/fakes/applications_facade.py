from uuid import UUID

from src.core.exceptions.exceptions import NotFoundError
from src.modules.applications.facade import (
    ACTIVE_STATUSES,
    ApplicationCardDTO,
    ApplicationSummaryDTO,
    CompletenessDTO,
    DocumentDTO,
    ScoringInputDTO,
)
from tests.fakes import builders


class FakeApplicationsFacade:
    def __init__(self) -> None:
        self.cards: dict[UUID, ApplicationCardDTO] = {}
        self.completeness: dict[UUID, CompletenessDTO] = {}
        self.scoring_inputs: dict[UUID, ScoringInputDTO] = {}
        self.contents: dict[UUID, bytes] = {}

    def add_card(self, card: ApplicationCardDTO) -> ApplicationCardDTO:
        self.cards[card.id] = card
        return card

    def add_document_content(self, document_id: UUID, content: bytes) -> None:
        self.contents[document_id] = content

    def _card(self, application_id: UUID) -> ApplicationCardDTO:
        try:
            return self.cards[application_id]
        except KeyError:
            raise NotFoundError("Application not found") from None

    async def get_card(self, application_id: UUID) -> ApplicationCardDTO:
        return self._card(application_id)

    async def get_completeness(self, application_id: UUID) -> CompletenessDTO:
        self._card(application_id)
        return self.completeness.get(application_id, CompletenessDTO(application_id, True, (), ()))

    async def get_scoring_input(self, application_id: UUID) -> ScoringInputDTO:
        if application_id in self.scoring_inputs:
            return self.scoring_inputs[application_id]
        return builders.scoring_input(self._card(application_id))

    async def list_for_organization(
        self, organization_id: UUID, active_only: bool = False
    ) -> list[ApplicationSummaryDTO]:
        return [
            ApplicationSummaryDTO(
                id=c.id,
                number=c.number,
                organization_id=c.organization_id,
                product_code=c.product_code,
                amount=c.request.amount if c.request else None,
                term_months=c.request.term_months if c.request else None,
                status=c.status,
                client_stage=c.client_stage,
                updated_at=c.updated_at,
                submitted_at=c.submitted_at,
            )
            for c in self.cards.values()
            if c.organization_id == organization_id
            and (not active_only or c.status in ACTIVE_STATUSES)
        ]

    async def list_submitted(self, limit: int) -> list[ApplicationSummaryDTO]:
        cards = sorted(
            (c for c in self.cards.values() if c.status != "draft"),
            key=lambda c: c.updated_at,
            reverse=True,
        )
        return [
            ApplicationSummaryDTO(
                id=c.id,
                number=c.number,
                organization_id=c.organization_id,
                product_code=c.product_code,
                amount=c.request.amount if c.request else None,
                term_months=c.request.term_months if c.request else None,
                status=c.status,
                client_stage=c.client_stage,
                updated_at=c.updated_at,
                submitted_at=c.submitted_at,
                company_name=c.org_snapshot.name if c.org_snapshot else None,
            )
            for c in cards[:limit]
        ]

    async def list_documents(
        self, application_id: UUID, document_type: str | None = None
    ) -> list[DocumentDTO]:
        return [
            d
            for d in self._card(application_id).documents
            if document_type is None or d.type == document_type
        ]

    async def read_document(self, application_id: UUID, document_id: UUID) -> bytes:
        if not any(d.id == document_id for d in self._card(application_id).documents):
            raise NotFoundError("Document not found")
        return self.contents.get(document_id, b"")
