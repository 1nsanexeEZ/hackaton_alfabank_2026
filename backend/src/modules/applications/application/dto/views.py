"""What the applications API answers: the application as its client sees it,
the contract to sign and the results of commands."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from src.modules.applications.application.dto.applications import (
    CollateralDTO,
    ConsentsDTO,
    DecisionSummaryDTO,
    DocumentDTO,
    InfoRequestDTO,
    OfferDTO,
    StatusChangeDTO,
)
from src.modules.applications.application.dto.drafts import DraftRequestDTO
from src.modules.applications.application.interfaces.storage import PresignedUpload
from src.modules.clients.facade import OrganizationSnapshotDTO
from src.modules.products.facade import PaymentScheduleDTO, ProductTermsDTO


@dataclass(frozen=True, slots=True)
class DisbursementDTO:
    reference: str
    disbursed_at: datetime
    # Paid out through the mock of the core banking system.
    simulated: bool


@dataclass(frozen=True, slots=True)
class ApplicationViewDTO:
    id: UUID
    number: str
    organization_id: UUID
    product_code: str
    status: str
    client_stage: str | None
    version: int
    request: DraftRequestDTO
    product_fields: dict[str, Any]
    collateral: CollateralDTO | None
    consents: ConsentsDTO
    product_terms: ProductTermsDTO
    # Company requisites as stored: the snapshot taken at submission, live
    # data for a draft.
    organization: dict[str, Any] | None
    documents: tuple[DocumentDTO, ...]
    info_requests: tuple[InfoRequestDTO, ...]
    offer: OfferDTO | None
    decision_summary: DecisionSummaryDTO | None
    disbursement: DisbursementDTO | None
    history: tuple[StatusChangeDTO, ...]
    # What the current user can do now — the frontend shows only these buttons.
    available_actions: tuple[str, ...]
    my_permissions: tuple[str, ...]
    created_at: datetime
    updated_at: datetime
    submitted_at: datetime | None
    closed_at: datetime | None


@dataclass(frozen=True, slots=True)
class CompletenessReportDTO:
    complete: bool
    # Violation.as_dict(): `code`, `field` and the parameters of the rule.
    violations: tuple[dict[str, Any], ...]


@dataclass(frozen=True, slots=True)
class DocumentUploadDTO:
    document: DocumentDTO
    upload: PresignedUpload


@dataclass(frozen=True, slots=True)
class ContractSignerDTO:
    account_id: UUID
    name: str
    # Head of the company by the registry, or a member with a power of attorney.
    authority: Literal["registry", "power_of_attorney"]


@dataclass(frozen=True, slots=True)
class ContractSignatureDTO:
    signed_by: UUID
    signed_at: datetime
    edo_document_id: str | None
    simulated: bool


@dataclass(frozen=True, slots=True)
class ContractDTO:
    """What the client signs: the offer, the schedule it gives and who may
    sign. Rendered by the frontend from these fields."""

    number: str
    offer_hash: str
    status: Literal["unsigned", "signed"]
    borrower: OrganizationSnapshotDTO
    signers: tuple[ContractSignerDTO, ...]
    terms: OfferDTO
    schedule: PaymentScheduleDTO
    signature: ContractSignatureDTO | None


@dataclass(frozen=True, slots=True)
class SignatureDTO:
    signed_at: datetime
    offer_hash: str
    edo_document_id: str
    # Signing goes through a mock of the document flow, not a real signature.
    simulated: bool


@dataclass(frozen=True, slots=True)
class SignResultDTO:
    application: ApplicationViewDTO
    signature: SignatureDTO
