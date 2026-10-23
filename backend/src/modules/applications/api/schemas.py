from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from src.core.types import SafeString

Amount = Annotated[Decimal, Field(gt=0, max_digits=15, decimal_places=2)]


# --- input --------------------------------------------------------------------


class ApplicationCreate(BaseModel):
    organization_id: UUID
    product_code: str = Field(min_length=1, max_length=64)


class LoanRequestIn(BaseModel):
    amount: Amount | None = None
    term_months: int | None = Field(default=None, ge=1, le=360)
    purpose: str | None = Field(default=None, max_length=64)
    purpose_comment: Annotated[SafeString, Field(max_length=500)] | None = None


class CollateralIn(BaseModel):
    type: Literal["real_estate", "equipment", "vehicle", "goods"]
    description: Annotated[SafeString, Field(min_length=1, max_length=1000)]
    declared_value: Amount
    owner: Literal["self", "third_party"] = "self"


class ConsentsIn(BaseModel):
    personal_data: bool
    credit_bureau: bool


class ApplicationUpdate(BaseModel):
    """Autosave of a draft. Send only what changed; `collateral: null` removes it."""

    version: int
    request: LoanRequestIn | None = None
    product_fields: dict[str, Any] | None = None
    collateral: CollateralIn | None = None
    consents: ConsentsIn | None = None


class DocumentUploadIn(BaseModel):
    type: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z_]*$")
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=1, max_length=128)
    size_bytes: int = Field(gt=0)


class ReasonIn(BaseModel):
    reason: Annotated[SafeString, Field(max_length=500)] | None = None


class SignIn(BaseModel):
    password: SecretStr = Field(min_length=1, max_length=128)
    # `offer_hash` from GET /applications/{id}/contract: the client signs what it saw.
    offer_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


# --- output -------------------------------------------------------------------


class LoanRequestOut(BaseModel):
    amount: Decimal | None
    term_months: int | None
    purpose: str | None
    purpose_comment: str | None


class CollateralOut(BaseModel):
    type: str
    description: str
    declared_value: Decimal
    owner: str


class ConsentsOut(BaseModel):
    personal_data_at: datetime | None
    credit_bureau_at: datetime | None


class RequiredDocumentOut(BaseModel):
    type: str
    title: str
    required_from_amount: Decimal | None
    legal_forms: list[str]


class ProductTermsOut(BaseModel):
    code: str
    version: int
    amount_min: Decimal
    amount_max: Decimal
    term_min_months: int
    term_max_months: int
    rate_base: Decimal
    rate_max: Decimal
    repayment_options: list[str]
    collateral_required: bool
    collateral_required_from: Decimal | None
    required_documents: list[RequiredDocumentOut]
    application_fields_schema: dict[str, Any]


class OrganizationOut(BaseModel):
    """Prefilled company requisites: the client does not type them."""

    model_config = ConfigDict(extra="ignore")

    id: UUID
    name: str
    inn: str
    ogrn: str
    kpp: str | None = None
    legal_form: str
    okved_main: str
    registered_at: date
    business_age_months: int
    head_name: str | None = None
    verification_status: str


class DocumentOut(BaseModel):
    id: UUID
    type: str
    filename: str
    content_type: str
    size_bytes: int
    status: str
    uploaded_at: datetime | None
    info_request_id: UUID | None


class InfoRequestOut(BaseModel):
    id: UUID
    requested_fields: list[str]
    requested_documents: list[str]
    comment: str
    status: str
    created_at: datetime
    due_at: datetime | None
    answered_at: datetime | None


class OfferOut(BaseModel):
    kind: str
    amount: Decimal
    term_months: int
    rate: Decimal
    monthly_payment: Decimal
    schedule_type: str
    conditions: list[str]
    expires_at: datetime


class DecisionSummaryOut(BaseModel):
    outcome: str
    client_explanation: str
    improvement_hints: list[str]
    alternative_product_code: str | None


class DisbursementOut(BaseModel):
    reference: str
    disbursed_at: datetime
    # Paid out through the mock of the core banking system.
    simulated: bool


class StatusChangeOut(BaseModel):
    from_status: str | None
    to_status: str
    at: datetime
    actor: str
    reason: str | None


class ApplicationOut(BaseModel):
    id: UUID
    number: str
    organization_id: UUID
    product_code: str
    status: str
    client_stage: str | None
    version: int
    request: LoanRequestOut
    product_fields: dict[str, Any]
    collateral: CollateralOut | None
    consents: ConsentsOut
    product_terms: ProductTermsOut
    organization: OrganizationOut | None
    documents: list[DocumentOut]
    info_requests: list[InfoRequestOut]
    offer: OfferOut | None
    decision_summary: DecisionSummaryOut | None
    disbursement: DisbursementOut | None
    history: list[StatusChangeOut]
    # What the current user can do now — the frontend shows only these buttons.
    available_actions: list[str]
    my_permissions: list[str]
    created_at: datetime
    updated_at: datetime
    submitted_at: datetime | None
    closed_at: datetime | None


class ApplicationListItem(BaseModel):
    id: UUID
    number: str
    organization_id: UUID
    product_code: str
    status: str
    client_stage: str | None
    amount: Decimal | None
    term_months: int | None
    updated_at: datetime
    submitted_at: datetime | None


class PresignedUploadOut(BaseModel):
    url: str
    method: str
    headers: dict[str, str]
    expires_at: datetime


class DocumentUploadOut(BaseModel):
    document: DocumentOut
    upload: PresignedUploadOut


class DownloadOut(BaseModel):
    url: str


class ViolationOut(BaseModel):
    model_config = ConfigDict(extra="allow")

    code: str
    field: str


class CompletenessOut(BaseModel):
    complete: bool
    violations: list[ViolationOut]


class SignatureOut(BaseModel):
    signed_at: datetime
    offer_hash: str
    edo_document_id: str
    # Signing goes through a mock of the document flow, not a real signature.
    simulated: bool


class SignOut(BaseModel):
    application: ApplicationOut
    signature: SignatureOut


class ContractBorrowerOut(BaseModel):
    name: str
    inn: str
    ogrn: str
    kpp: str | None
    legal_form: str
    head_name: str | None


class ContractSignerOut(BaseModel):
    account_id: UUID
    name: str
    authority: Literal["registry", "power_of_attorney"]


class ContractPaymentOut(BaseModel):
    number: int
    due_date: date | None
    principal: Decimal
    interest: Decimal
    total: Decimal
    balance_after: Decimal


class ContractScheduleOut(BaseModel):
    amount: Decimal
    term_months: int
    rate: Decimal
    repayment: str
    monthly_payment: Decimal
    total_interest: Decimal
    total_paid: Decimal
    payments: list[ContractPaymentOut]


class ContractSignatureOut(BaseModel):
    signed_by: UUID
    signed_at: datetime
    edo_document_id: str | None
    simulated: bool


class ContractOut(BaseModel):
    """The loan contract to show before signing. `number` is the application
    number; `offer_hash` goes back in `POST /applications/{id}/sign`."""

    number: str
    offer_hash: str
    status: Literal["unsigned", "signed"]
    borrower: ContractBorrowerOut
    signers: list[ContractSignerOut]
    terms: OfferOut
    schedule: ContractScheduleOut
    signature: ContractSignatureOut | None
