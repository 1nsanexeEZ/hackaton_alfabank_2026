from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.core.types import SafeString
from src.modules.applications.application.dto.applications import CollateralDTO
from src.modules.applications.application.dto.common import UNSET
from src.modules.applications.application.dto.drafts import (
    ConsentsChoiceDTO,
    DraftChangesDTO,
    DraftRequestDTO,
)
from src.modules.applications.presentation.schemas.documents import DocumentOut

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

    def to_dto(self) -> DraftRequestDTO:
        return DraftRequestDTO(
            amount=self.amount,
            term_months=self.term_months,
            purpose=self.purpose,
            purpose_comment=self.purpose_comment,
        )


class CollateralIn(BaseModel):
    type: Literal["real_estate", "equipment", "vehicle", "goods"]
    description: Annotated[SafeString, Field(min_length=1, max_length=1000)]
    declared_value: Amount
    owner: Literal["self", "third_party"] = "self"

    def to_dto(self) -> CollateralDTO:
        return CollateralDTO(
            type=self.type,
            description=self.description,
            declared_value=self.declared_value,
            owner=self.owner,
        )


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

    def to_dto(self) -> DraftChangesDTO:
        """Fields that weren't sent are UNSET; null stays None."""
        sent = self.model_fields_set
        request = self.request.to_dto() if self.request else None
        collateral = self.collateral.to_dto() if self.collateral else None
        consents = (
            ConsentsChoiceDTO(self.consents.personal_data, self.consents.credit_bureau)
            if self.consents
            else None
        )
        return DraftChangesDTO(
            version=self.version,
            request=request if "request" in sent else UNSET,
            product_fields=self.product_fields if "product_fields" in sent else UNSET,
            collateral=collateral if "collateral" in sent else UNSET,
            consents=consents if "consents" in sent else UNSET,
        )


class ReasonIn(BaseModel):
    reason: Annotated[SafeString, Field(max_length=500)] | None = None


# --- output -------------------------------------------------------------------


class LoanRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    amount: Decimal | None
    term_months: int | None
    purpose: str | None
    purpose_comment: str | None


class CollateralOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    type: str
    description: str
    declared_value: Decimal
    owner: str


class ConsentsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    personal_data_at: datetime | None
    credit_bureau_at: datetime | None


class RequiredDocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    type: str
    title: str
    required_from_amount: Decimal | None
    legal_forms: list[str]


class ProductTermsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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


class InfoRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    requested_fields: list[str]
    requested_documents: list[str]
    comment: str
    status: str
    created_at: datetime
    due_at: datetime | None
    answered_at: datetime | None


class OfferOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    kind: str
    amount: Decimal
    term_months: int
    rate: Decimal
    monthly_payment: Decimal
    schedule_type: str
    conditions: list[str]
    expires_at: datetime


class DecisionSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    outcome: str
    client_explanation: str
    improvement_hints: list[str]
    alternative_product_code: str | None


class DisbursementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    reference: str
    disbursed_at: datetime
    # Paid out through the mock of the core banking system.
    simulated: bool


class StatusChangeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    from_status: str | None
    to_status: str
    at: datetime
    actor: str
    reason: str | None


class ApplicationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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
    model_config = ConfigDict(from_attributes=True)

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


class ViolationOut(BaseModel):
    model_config = ConfigDict(extra="allow")

    code: str
    field: str


class CompletenessOut(BaseModel):
    complete: bool
    violations: list[ViolationOut]
