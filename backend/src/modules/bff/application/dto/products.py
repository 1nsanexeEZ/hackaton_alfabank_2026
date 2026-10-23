from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Self

from src.modules.bff.domain.enums import PreApprovalBasis
from src.modules.products.facade import EligibilityReasonDTO, PaymentScheduleDTO, Repayment


@dataclass(frozen=True, slots=True)
class ReasonDTO:
    code: str
    passed: bool
    message: str

    @classmethod
    def of(cls, reason: EligibilityReasonDTO) -> Self:
        return cls(code=reason.code, passed=reason.passed, message=reason.message)


# --- product matching ---------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RecommendationItemDTO:
    product_code: str
    product_name: str
    short_description: str
    rank: int
    # best — the first product that fits; unavailable — the company does not fit.
    fit: str
    eligible: bool | None
    eligibility: tuple[ReasonDTO, ...]
    rate_from: Decimal
    amount_max: Decimal
    term_max_months: int
    payment_from: Decimal | None
    pre_approved_max: Decimal | None


@dataclass(frozen=True, slots=True)
class RecommendationsDTO:
    items: tuple[RecommendationItemDTO, ...]
    degraded: tuple[str, ...]


# --- calculator with the pre-approval -----------------------------------------


@dataclass(frozen=True, slots=True)
class CalculationDTO:
    amount: Decimal
    term_months: int
    # The default schedule of the product when None.
    repayment: Repayment | None


@dataclass(frozen=True, slots=True)
class PreApprovedTermsDTO:
    max_amount: Decimal
    rate_from: Decimal
    term_max_months: int
    valid_until: date
    basis: PreApprovalBasis


@dataclass(frozen=True, slots=True)
class SuggestionDTO:
    amount: Decimal
    term_months: int
    monthly_payment: Decimal


@dataclass(frozen=True, slots=True)
class PersonalScheduleDTO:
    # At the pre-approved rate; at the base rate of the product without a pre-approval.
    schedule: PaymentScheduleDTO
    pre_approved: PreApprovedTermsDTO | None
    # None — nothing is pre-approved for this product, nothing to compare with.
    within_pre_approved: bool | None
    eligible: bool
    # Eligibility reasons and what is above the pre-approved terms.
    reasons: tuple[ReasonDTO, ...]
    # The request cut to the pre-approved terms; None when it fits or nothing is pre-approved.
    suggestion: SuggestionDTO | None
    degraded: tuple[str, ...]
