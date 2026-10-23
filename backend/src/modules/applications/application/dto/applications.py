"""The application card and what other modules read about it (re-exported by
`facade.py`)."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from src.modules.clients.facade import OrganizationSnapshotDTO
from src.modules.products.facade import ProductTermsDTO

ApplicationStatus = Literal[
    "draft",
    "submitted",
    "in_review",
    "info_requested",
    "offer_ready",
    "signing",
    "signed",
    "disbursed",
    "rejected",
    "offer_declined",
    "expired",
    "cancelled",
]
ACTIVE_STATUSES: frozenset[str] = frozenset(
    {"draft", "submitted", "in_review", "info_requested", "offer_ready", "signing", "signed"}
)
DocumentStatus = Literal["pending_upload", "uploaded", "accepted", "rejected"]
CollateralType = Literal["real_estate", "equipment", "vehicle", "goods"]


@dataclass(frozen=True, slots=True)
class LoanRequestDTO:
    amount: Decimal
    term_months: int
    purpose: str
    purpose_comment: str | None = None


@dataclass(frozen=True, slots=True)
class CollateralDTO:
    type: CollateralType
    description: str
    declared_value: Decimal
    owner: Literal["self", "third_party"]


@dataclass(frozen=True, slots=True)
class ConsentsDTO:
    personal_data_at: datetime | None
    credit_bureau_at: datetime | None
    given_by: UUID | None
    automated_decision_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class DocumentDTO:
    id: UUID
    type: str
    filename: str
    content_type: str
    size_bytes: int
    status: DocumentStatus
    uploaded_by: UUID | None
    uploaded_at: datetime | None
    info_request_id: UUID | None = None
    review_comment: str | None = None


@dataclass(frozen=True, slots=True)
class InfoRequestDTO:
    id: UUID
    requested_fields: tuple[str, ...]
    requested_documents: tuple[str, ...]
    comment: str
    created_at: datetime
    due_at: datetime | None
    status: Literal["open", "answered", "expired"]
    answered_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class OfferDTO:
    kind: Literal["as_requested", "counter"]
    amount: Decimal
    term_months: int
    rate: Decimal
    monthly_payment: Decimal
    schedule_type: str
    conditions: tuple[str, ...]
    expires_at: datetime
    decision_id: UUID


@dataclass(frozen=True, slots=True)
class DecisionSummaryDTO:
    """What the client may see about the decision: no reason codes, no score."""

    outcome: str
    client_explanation: str
    improvement_hints: tuple[str, ...]
    alternative_product_code: str | None = None


@dataclass(frozen=True, slots=True)
class StatusChangeDTO:
    from_status: str | None
    to_status: str
    at: datetime
    actor: str
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class ApplicationCardDTO:
    id: UUID
    number: str
    organization_id: UUID
    applicant_account_id: UUID
    product_code: str
    product_terms: ProductTermsDTO
    request: LoanRequestDTO | None
    product_fields: dict[str, Any]
    collateral: CollateralDTO | None
    consents: ConsentsDTO | None
    org_snapshot: OrganizationSnapshotDTO | None
    status: ApplicationStatus
    client_stage: str | None
    documents: tuple[DocumentDTO, ...]
    info_requests: tuple[InfoRequestDTO, ...]
    offer: OfferDTO | None
    decision_summary: DecisionSummaryDTO | None
    history: tuple[StatusChangeDTO, ...]
    version: int
    created_at: datetime
    updated_at: datetime
    submitted_at: datetime | None = None
    closed_at: datetime | None = None
    # Loan contract number from the core banking system once paid out.
    disbursement_reference: str | None = None


@dataclass(frozen=True, slots=True)
class CompletenessDTO:
    application_id: UUID
    complete: bool
    missing_fields: tuple[str, ...]
    missing_documents: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ScoringInputDTO:
    """Everything scoring and decision need, frozen at submission."""

    application_id: UUID
    organization_id: UUID
    product_code: str
    request: LoanRequestDTO
    organization: OrganizationSnapshotDTO
    product_terms: ProductTermsDTO
    collateral: CollateralDTO | None
    statement_document_ids: tuple[UUID, ...]
    credit_bureau_consent_at: datetime | None
    submitted_at: datetime
    # Who submitted it: screened as a representative under 115-FZ.
    applicant_account_id: UUID | None = None
    # Consent to a decision made solely by automated processing (152-FZ art. 16).
    automated_decision_consent_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ApplicationSummaryDTO:
    id: UUID
    number: str
    organization_id: UUID
    product_code: str
    amount: Decimal | None
    term_months: int | None
    status: ApplicationStatus
    client_stage: str | None
    updated_at: datetime
    submitted_at: datetime | None = None
