from datetime import date
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from src.core.domain import Money
from src.modules.products.application import mappers
from src.modules.products.domain.calculator import PaymentSchedule
from src.modules.products.domain.product import CreditProduct
from src.modules.products.domain.product import ProductStatus as Status
from src.modules.products.domain.recommender import Recommendation, RecommendationStatus
from src.modules.products.domain.value_objects import (
    MAX_TERM_MONTHS,
    AmountRange,
    DocumentRequirement,
    Eligibility,
    EligibilityCheck,
    ProcessingProfile,
    ProductCode,
    RateRange,
    SecurityRequirement,
    SupportProgram,
    TermRange,
)
from src.modules.products.facade import (
    CollateralKind,
    Facility,
    Guarantee,
    ProductStatus,
    Purpose,
    Repayment,
)


def _cents(value: Decimal) -> Decimal:
    """As the database keeps it: the answer to a write is the same as a read, `22.00`."""
    return value.quantize(Decimal("0.01"))


Amount = Annotated[Decimal, Field(gt=0, max_digits=18, decimal_places=2)]
# Terms of a product.
ProductAmount = Annotated[Amount, AfterValidator(_cents)]
# Limits that may be zero: the auto decision limit, the minimum revenue.
Limit = Annotated[Decimal, Field(ge=0, max_digits=18, decimal_places=2), AfterValidator(_cents)]
Rate = Annotated[
    Decimal, Field(ge=0, le=100, max_digits=5, decimal_places=2), AfterValidator(_cents)
]
TermMonths = Annotated[int, Field(ge=1, le=MAX_TERM_MONTHS)]
LegalForm = Literal["LLC", "IE", "JSC"]
# The same values the application accepts in its collateral declaration.
CollateralType = Literal["real_estate", "equipment", "vehicle", "goods"]


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


class RequiredDocumentBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # `financial_report`: the application expects a document of this type.
    type: Annotated[str, Field(max_length=64)]
    title: Annotated[str, Field(max_length=200)]
    # Required only from this amount; none — at any amount.
    required_from_amount: ProductAmount | None = None
    # Required only for these legal forms; empty — for every form.
    legal_forms: list[LegalForm] = []

    def requirement(self) -> DocumentRequirement:
        return DocumentRequirement(
            type=self.type,
            title=self.title,
            required_from=_money(self.required_from_amount),
            legal_forms=frozenset(self.legal_forms),
        )


class SupportProgramBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: Annotated[str, Field(max_length=32)]
    name: Annotated[str, Field(max_length=200)]
    # The client is offered no more than this rate.
    rate_cap: Rate
    msp_registry_required: bool = True
    # Two-digit OKVED classes; empty — any industry.
    okved_whitelist: list[str] = []

    def program(self) -> SupportProgram:
        return SupportProgram(
            code=self.code,
            name=self.name,
            rate_cap=self.rate_cap,
            msp_registry_required=self.msp_registry_required,
            okved_whitelist=frozenset(self.okved_whitelist),
        )


class ProductBody(BaseModel):
    """Terms of a product, as in `ProductRead`: the code is in the path, the
    version and the status are set by the catalog."""

    model_config = ConfigDict(extra="forbid")

    frontend_id: Annotated[str, Field(max_length=32)]
    name: Annotated[str, Field(max_length=200)]
    short_description: Annotated[str, Field(max_length=500)]
    description_plain: str = ""
    purposes: list[Purpose]
    facility: Facility
    # The first one is the default schedule.
    repayment_options: list[Repayment]
    amount_min: ProductAmount
    amount_max: ProductAmount
    term_min_months: TermMonths
    term_max_months: TermMonths
    rate_base: Rate
    rate_max: Rate
    collateral_kind: CollateralKind = "none"
    collateral_types: list[CollateralType] = []
    # Optional collateral becomes required from this amount.
    collateral_required_from: ProductAmount | None = None
    guarantee: Guarantee = "none"
    # Money goes to a stated target (a vehicle, a property, other loans).
    target_use_confirmation: bool = False
    support_program: SupportProgramBody | None = None
    min_business_age_months: Annotated[int, Field(ge=0)] = 0
    allowed_legal_forms: list[LegalForm] = ["LLC", "IE", "JSC"]
    min_annual_revenue: Limit | None = None
    # Only for a company without turnover: younger than 6 months or without an annual report.
    startup_only: bool = False
    required_documents: list[RequiredDocumentBody] = []
    # JSON Schema of the extra application fields: the subset applications understand.
    application_fields_schema: dict[str, Any] = {}
    # A route of the process module (GET /workflows).
    workflow_code: Annotated[str, Field(max_length=64)]
    # Up to this amount the decision may be taken without an underwriter.
    auto_decision_limit: Limit

    def product(self, code: str) -> CreditProduct:
        """A draft of version 1 until the catalog says otherwise."""
        program = self.support_program
        return CreditProduct(
            code=ProductCode(code),
            version=1,
            status=Status.DRAFT,
            name=self.name,
            short_description=self.short_description,
            description_plain=self.description_plain,
            frontend_id=self.frontend_id,
            purposes=frozenset(self.purposes),
            facility=self.facility,
            repayment_options=tuple(self.repayment_options),
            amount=AmountRange(Money(self.amount_min), Money(self.amount_max)),
            term=TermRange(self.term_min_months, self.term_max_months),
            rate=RateRange(self.rate_base, self.rate_max),
            security=SecurityRequirement(
                collateral=self.collateral_kind,
                collateral_types=tuple(self.collateral_types),
                guarantee=self.guarantee,
                required_from=_money(self.collateral_required_from),
            ),
            eligibility=Eligibility(
                min_business_age_months=self.min_business_age_months,
                allowed_legal_forms=frozenset(self.allowed_legal_forms),
                min_annual_revenue=_money(self.min_annual_revenue),
                startup_only=self.startup_only,
            ),
            processing=ProcessingProfile(self.workflow_code, Money(self.auto_decision_limit)),
            required_documents=tuple(d.requirement() for d in self.required_documents),
            support_program=None if program is None else program.program(),
            target_use_confirmation=self.target_use_confirmation,
            application_fields_schema=self.application_fields_schema,
        )


class ProductCreate(ProductBody):
    # `UNSECURED`, `GOV_SUPPORT`: the same in every version of the product.
    code: Annotated[str, Field(max_length=32)]
    # A draft is not in the catalog until it is activated.
    status: Literal["draft", "active"] = "draft"


def _money(amount: Decimal | None) -> Money | None:
    return None if amount is None else Money(amount)


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
    # From the latest bank statement forecast (enrichment); None — no statement yet or no
    # company given, the gap is unknown.
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
