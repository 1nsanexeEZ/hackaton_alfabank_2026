"""Applications contract (read only): the application card is the source of
truth for its status and offer; lists for screens come from the projector.

The only entry point for other modules: the protocol below and the DTO it returns
(defined in `application/dto`, re-exported here)."""

from typing import Protocol
from uuid import UUID

from src.modules.applications.application.dto.applications import (
    ACTIVE_STATUSES,
    ApplicationCardDTO,
    ApplicationStatus,
    ApplicationSummaryDTO,
    CollateralDTO,
    CollateralType,
    CompletenessDTO,
    ConsentsDTO,
    DecisionSummaryDTO,
    DocumentDTO,
    DocumentStatus,
    InfoRequestDTO,
    LoanRequestDTO,
    OfferDTO,
    ScoringInputDTO,
    StatusChangeDTO,
)

__all__ = [
    "ACTIVE_STATUSES",
    "ApplicationCardDTO",
    "ApplicationStatus",
    "ApplicationSummaryDTO",
    "ApplicationsFacade",
    "CollateralDTO",
    "CollateralType",
    "CompletenessDTO",
    "ConsentsDTO",
    "DecisionSummaryDTO",
    "DocumentDTO",
    "DocumentStatus",
    "InfoRequestDTO",
    "LoanRequestDTO",
    "OfferDTO",
    "ScoringInputDTO",
    "StatusChangeDTO",
]


class ApplicationsFacade(Protocol):
    async def get_card(self, application_id: UUID) -> ApplicationCardDTO:
        """Raises NotFoundError."""
        ...

    async def get_completeness(self, application_id: UUID) -> CompletenessDTO: ...

    async def get_scoring_input(self, application_id: UUID) -> ScoringInputDTO: ...

    async def list_for_organization(
        self, organization_id: UUID, active_only: bool = False
    ) -> list[ApplicationSummaryDTO]: ...

    async def list_documents(
        self, application_id: UUID, document_type: str | None = None
    ) -> list[DocumentDTO]: ...

    async def read_document(self, application_id: UUID, document_id: UUID) -> bytes:
        """Content of an uploaded document (bank statements for the cash flow forecast)."""
        ...
