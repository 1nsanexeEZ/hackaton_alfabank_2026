from datetime import date
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.modules.products.application import mappers
from src.modules.products.domain.calculator import PaymentSchedule
from src.modules.products.domain.product import CreditProduct
from src.modules.products.domain.recommender import Recommendation, RecommendationStatus
from src.modules.products.domain.value_objects import MAX_TERM_MONTHS, EligibilityCheck
from src.modules.products.facade import (
    CollateralKind,
    Facility,
    Guarantee,
    ProductStatus,
    Purpose,
    Repayment,
)

Amount = Annotated[Decimal, Field(gt=0, max_digits=18, decimal_places=2)]
TermMonths = Annotated[int, Field(ge=1, le=MAX_TERM_MONTHS)]


class _Read(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class RequiredDocumentRead(_Read):
    type: str
    title: str
    required_from_amount: Decimal | None
    legal_forms: list[str]


class SupportProgramRead(_Read):
    code: str
    name: str
    rate_cap: Decimal
    msp_registry_required: bool
    okved_whitelist: list[str]


class ProductRead(_Read):
    code: str
    frontend_id: str
    version: int
    name: str
    short_description: str
    description_plain: str
    purposes: list[Purpose]
    facility: Facility
    repayment_options: list[Repayment]
    amount_min: Decimal
    amount_max: Decimal
    term_min_months: int
    term_max_months: int
    rate_base: Decimal
    rate_max: Decimal
    collateral_kind: CollateralKind
    collateral_required_from: Decimal | None
    collateral_types: list[str]
    guarantee: Guarantee
    target_use_confirmation: bool
    support_program: SupportProgramRead | None
    min_business_age_months: int
    allowed_legal_forms: list[str]
    min_annual_revenue: Decimal | None
    required_documents: list[RequiredDocumentRead]
    application_fields_schema: dict[str, Any]
    workflow_code: str
    auto_decision_limit: Decimal
    status: ProductStatus
    # Only for a company without turnover: younger than 6 months or without an annual report.
    startup_only: bool

    @classmethod
    def of(cls, product: CreditProduct) -> "ProductRead":
        return cls.model_validate(mappers.product_dto(product))


class ReasonRead(_Read):
    code: str
    passed: bool
    message: str


class EligibilityRead(BaseModel):
    product_code: str
    organization_id: UUID
    eligible: bool
    reasons: list[ReasonRead]

    @classmethod
    def of(cls, check: EligibilityCheck, organization_id: UUID) -> "EligibilityRead":
        return cls.model_validate(mappers.check_dto(check, organization_id), from_attributes=True)


class NeedBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    purpose: Purpose
    amount: Amount
    term_months: TermMonths


class RecommendationRead(BaseModel):
    rank: int
    # available — fits and may be chosen; needs_adjustment — change the amount
    # or term (see adjustments); unavailable — the company does not qualify.
    status: RecommendationStatus
    eligible: bool | None
    fits: bool
    reasons: list[ReasonRead]
    adjustments: list[str]
    repayment: Repayment
    # The estimate is for the nearest amount and term the product allows.
    amount: Decimal
    term_months: int
    monthly_payment_from: Decimal
    monthly_payment_to: Decimal
    product: ProductRead

    @classmethod
    def of(cls, recommendation: Recommendation) -> "RecommendationRead":
        return cls(
            rank=recommendation.rank,
            status=recommendation.status,
            eligible=recommendation.eligible,
            fits=recommendation.fits,
            reasons=[ReasonRead.model_validate(r) for r in recommendation.reasons],
            adjustments=list(recommendation.adjustments),
            repayment=recommendation.repayment,  # type: ignore[arg-type]
            amount=recommendation.amount.amount,
            term_months=recommendation.term_months,
            monthly_payment_from=recommendation.monthly_payment_from.amount,
            monthly_payment_to=recommendation.monthly_payment_to.amount,
            product=ProductRead.of(recommendation.product),
        )


class RecommendationsRead(BaseModel):
    purpose: Purpose
    amount: Decimal
    term_months: int
    organization_id: UUID | None = None
    # From the scoring forecast; None — unknown or no company given.
    cash_gap_expected: bool | None = None
    items: list[RecommendationRead]


class CalculateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: Amount
    term_months: TermMonths
    # Annual percent; the base rate of the product when omitted.
    rate: Annotated[Decimal | None, Field(ge=0, le=100, max_digits=5, decimal_places=2)] = None
    # The default schedule of the product when omitted.
    repayment: Repayment | None = None


class PaymentRead(_Read):
    number: int
    due_date: date | None
    principal: Decimal
    interest: Decimal
    total: Decimal
    balance_after: Decimal


class PaymentScheduleRead(_Read):
    amount: Decimal
    term_months: int
    rate: Decimal
    repayment: Repayment
    monthly_payment: Decimal
    total_interest: Decimal
    total_paid: Decimal
    payments: list[PaymentRead]

    @classmethod
    def of(cls, schedule: PaymentSchedule) -> "PaymentScheduleRead":
        return cls.model_validate(mappers.schedule_dto(schedule))
