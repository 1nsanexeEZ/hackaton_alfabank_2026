"""Products contract: catalog, product matching and the single payment formula."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Literal, Protocol
from uuid import UUID

Purpose = Literal[
    "working_capital",
    "cash_gap",
    "equipment",
    "vehicles",
    "real_estate",
    "contract_execution",
    "refinancing",
    "expansion",
]
Facility = Literal["term_loan", "credit_line_revolving", "credit_line_non_revolving", "overdraft"]
Repayment = Literal["annuity", "differentiated", "interest_only", "by_contract_schedule"]
CollateralKind = Literal["none", "optional", "required"]
Guarantee = Literal["none", "owner", "msp_corporation"]
ProductStatus = Literal["draft", "active", "archived"]


@dataclass(frozen=True, slots=True)
class RequiredDocumentDTO:
    type: str
    title: str
    # Required only from this amount (None — always).
    required_from_amount: Decimal | None = None


@dataclass(frozen=True, slots=True)
class SupportProgramDTO:
    code: str
    name: str
    rate_cap: Decimal
    msp_registry_required: bool
    okved_whitelist: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProductDTO:
    code: str
    frontend_id: str
    version: int
    name: str
    short_description: str
    description_plain: str
    purposes: tuple[Purpose, ...]
    facility: Facility
    repayment_options: tuple[Repayment, ...]
    amount_min: Decimal
    amount_max: Decimal
    term_min_months: int
    term_max_months: int
    rate_base: Decimal
    rate_max: Decimal
    collateral_kind: CollateralKind
    collateral_required_from: Decimal | None
    collateral_types: tuple[str, ...]
    guarantee: Guarantee
    target_use_confirmation: bool
    support_program: SupportProgramDTO | None
    min_business_age_months: int
    allowed_legal_forms: tuple[str, ...]
    min_annual_revenue: Decimal | None
    required_documents: tuple[RequiredDocumentDTO, ...]
    # JSON schema of extra application form fields for this product.
    application_fields_schema: dict[str, Any]
    workflow_code: str
    auto_decision_limit: Decimal
    status: ProductStatus


@dataclass(frozen=True, slots=True)
class ProductTermsDTO:
    """Copy of the product terms stored in a draft application."""

    code: str
    version: int
    amount_min: Decimal
    amount_max: Decimal
    term_min_months: int
    term_max_months: int
    rate_base: Decimal
    rate_max: Decimal
    repayment_options: tuple[Repayment, ...]
    facility: Facility
    collateral_required: bool
    collateral_required_from: Decimal | None
    required_documents: tuple[RequiredDocumentDTO, ...]
    application_fields_schema: dict[str, Any]
    workflow_code: str
    auto_decision_limit: Decimal


@dataclass(frozen=True, slots=True)
class EligibilityReasonDTO:
    code: str
    passed: bool
    message: str


@dataclass(frozen=True, slots=True)
class EligibilityCheckDTO:
    product_code: str
    organization_id: UUID
    eligible: bool
    reasons: tuple[EligibilityReasonDTO, ...]


@dataclass(frozen=True, slots=True)
class RecommendationDTO:
    product: ProductDTO
    rank: int
    eligible: bool | None  # None — no organization given, eligibility not checked
    reasons: tuple[EligibilityReasonDTO, ...]
    estimated_monthly_payment: Decimal | None


@dataclass(frozen=True, slots=True)
class PaymentDTO:
    number: int
    due_date: date | None
    principal: Decimal
    interest: Decimal
    total: Decimal
    balance_after: Decimal


@dataclass(frozen=True, slots=True)
class PaymentScheduleDTO:
    amount: Decimal
    term_months: int
    rate: Decimal
    repayment: Repayment
    monthly_payment: Decimal  # first payment for non-annuity schedules
    total_interest: Decimal
    total_paid: Decimal
    payments: tuple[PaymentDTO, ...]


class ProductsFacade(Protocol):
    async def get_product(self, code: str) -> ProductDTO: ...

    async def list_active(self) -> list[ProductDTO]: ...

    async def get_terms_snapshot(self, code: str) -> ProductTermsDTO: ...

    async def check_eligibility(self, code: str, organization_id: UUID) -> EligibilityCheckDTO: ...

    async def recommend(
        self,
        purpose: Purpose,
        amount: Decimal,
        term_months: int,
        organization_id: UUID | None = None,
    ) -> list[RecommendationDTO]: ...

    def calculate_payment(
        self, amount: Decimal, term_months: int, rate: Decimal, repayment: Repayment
    ) -> PaymentScheduleDTO: ...
