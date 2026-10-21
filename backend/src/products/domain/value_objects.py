"""Value objects of a credit product: what it is for, its frames and who may get it."""

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from src.core.domain import Money
from src.core.exceptions.exceptions import ValidationError

# Canonical orders: DTOs and the database list values in this order.
PURPOSES: tuple[str, ...] = (
    "working_capital",
    "cash_gap",
    "equipment",
    "vehicles",
    "real_estate",
    "contract_execution",
    "refinancing",
    "expansion",
)
FACILITIES: tuple[str, ...] = (
    "term_loan",
    "credit_line_revolving",
    "credit_line_non_revolving",
    "overdraft",
)
REPAYMENTS: tuple[str, ...] = ("annuity", "differentiated", "interest_only", "by_contract_schedule")
COLLATERAL_KINDS: tuple[str, ...] = ("none", "optional", "required")
# The same values the application accepts in its collateral declaration.
COLLATERAL_TYPES: tuple[str, ...] = ("real_estate", "equipment", "vehicle", "goods")
GUARANTEES: tuple[str, ...] = ("none", "owner", "msp_corporation")
LEGAL_FORMS: tuple[str, ...] = ("LLC", "IE", "JSC")
MAX_TERM_MONTHS = 360
MAX_RATE = Decimal(100)

_SLUG = re.compile(r"^[a-z][a-z0-9_]*$")
_OKVED_CLASS = re.compile(r"^\d{2}$")


def invalid(field_name: str, code: str, message: str) -> ValidationError:
    return ValidationError(message, details={"field": field_name, "code": code})


def ordered(values: Iterable[str], canonical: tuple[str, ...]) -> tuple[str, ...]:
    """Values in the canonical order (unknown ones last, alphabetically)."""
    position = {value: index for index, value in enumerate(canonical)}
    return tuple(sorted(set(values), key=lambda v: (position.get(v, len(canonical)), v)))


def _require_decimal(value: Any, field_name: str) -> None:
    if not isinstance(value, Decimal):
        raise invalid(field_name, "not_decimal", f"{field_name} must be a Decimal")


@dataclass(frozen=True, slots=True)
class ProductCode:
    """`UNSECURED`, `GOV_SUPPORT`: stable across versions of the product."""

    value: str

    _PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{1,31}$")

    def __post_init__(self) -> None:
        if not self._PATTERN.match(self.value):
            raise invalid("code", "bad_format", f"Invalid product code {self.value!r}")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class AmountRange:
    min: Money
    max: Money

    def __post_init__(self) -> None:
        if self.min.currency != self.max.currency:
            raise invalid("amount", "currency_mismatch", "Amount range currencies differ")
        if not self.min.amount > 0:
            raise invalid("amount_min", "not_positive", "Minimum amount must be positive")
        if self.max < self.min:
            raise invalid("amount_max", "less_than_min", "Maximum amount is below the minimum")

    def contains(self, amount: Money) -> bool:
        return self.min <= amount <= self.max

    def clamp(self, amount: Money) -> Money:
        return min(max(amount, self.min), self.max)


@dataclass(frozen=True, slots=True)
class TermRange:
    min_months: int
    max_months: int

    def __post_init__(self) -> None:
        if self.min_months < 1:
            raise invalid("term_min_months", "not_positive", "Minimum term must be at least 1")
        if self.max_months > MAX_TERM_MONTHS:
            raise invalid("term_max_months", "too_large", "Term is too long")
        if self.max_months < self.min_months:
            raise invalid("term_max_months", "less_than_min", "Maximum term is below the minimum")

    def contains(self, months: int) -> bool:
        return self.min_months <= months <= self.max_months

    def clamp(self, months: int) -> int:
        return min(max(months, self.min_months), self.max_months)


@dataclass(frozen=True, slots=True)
class RateRange:
    """Annual rate in percent: `Decimal("23.5")` is 23.5 % per year."""

    base: Decimal
    max: Decimal

    def __post_init__(self) -> None:
        _require_decimal(self.base, "rate_base")
        _require_decimal(self.max, "rate_max")
        if self.base < 0:
            raise invalid("rate_base", "negative", "Rate can't be negative")
        if self.max > MAX_RATE:
            raise invalid("rate_max", "too_large", "Rate is too large")
        if self.max < self.base:
            raise invalid("rate_max", "less_than_base", "Maximum rate is below the base rate")

    def contains(self, rate: Decimal) -> bool:
        return self.base <= rate <= self.max


@dataclass(frozen=True, slots=True)
class SecurityRequirement:
    """Collateral and guarantee. `required_from` — optional collateral becomes
    mandatory from this amount."""

    collateral: str = "none"
    collateral_types: tuple[str, ...] = ()
    guarantee: str = "none"
    required_from: Money | None = None

    def __post_init__(self) -> None:
        if self.collateral not in COLLATERAL_KINDS:
            raise invalid("collateral_kind", "unknown", "Unknown collateral kind")
        if self.guarantee not in GUARANTEES:
            raise invalid("guarantee", "unknown", "Unknown guarantee")
        if len(set(self.collateral_types)) != len(self.collateral_types):
            raise invalid("collateral_types", "duplicate", "Collateral types repeat")
        if not set(self.collateral_types) <= set(COLLATERAL_TYPES):
            raise invalid("collateral_types", "unknown", "Unknown collateral type")
        if self.collateral == "none" and self.collateral_types:
            raise invalid("collateral_types", "not_expected", "No collateral, but types are set")
        if self.collateral != "none" and not self.collateral_types:
            raise invalid("collateral_types", "missing", "Collateral types are not set")
        if self.required_from is not None and self.collateral != "optional":
            raise invalid(
                "collateral_required_from",
                "not_expected",
                "A threshold makes sense only for optional collateral",
            )

    def needs_collateral(self, amount: Money | None) -> bool:
        if self.collateral == "required":
            return True
        return (
            self.required_from is not None and amount is not None and amount >= self.required_from
        )


@dataclass(frozen=True, slots=True)
class SupportProgram:
    """State support: a rate cap for small business from listed industries."""

    code: str
    name: str
    rate_cap: Decimal
    msp_registry_required: bool = True
    # Two-digit OKVED classes; empty — any industry.
    okved_whitelist: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if not self.code.strip() or not self.name.strip():
            raise invalid("support_program", "missing", "Support program needs a code and a name")
        _require_decimal(self.rate_cap, "support_program.rate_cap")
        if not all(_OKVED_CLASS.match(code) for code in self.okved_whitelist):
            raise invalid("support_program.okved_whitelist", "bad_format", "Use 2-digit OKVED")

    def covers(self, okved_class: str) -> bool:
        return not self.okved_whitelist or okved_class in self.okved_whitelist


@dataclass(frozen=True, slots=True)
class Eligibility:
    min_business_age_months: int = 0
    allowed_legal_forms: frozenset[str] = frozenset(LEGAL_FORMS)
    min_annual_revenue: Money | None = None

    def __post_init__(self) -> None:
        if self.min_business_age_months < 0:
            raise invalid("min_business_age_months", "negative", "Business age can't be negative")
        if not self.allowed_legal_forms:
            raise invalid("allowed_legal_forms", "missing", "Allow at least one legal form")
        if not self.allowed_legal_forms <= set(LEGAL_FORMS):
            raise invalid("allowed_legal_forms", "unknown", "Unknown legal form")
        if self.min_annual_revenue is not None and self.min_annual_revenue.is_negative:
            raise invalid("min_annual_revenue", "negative", "Revenue can't be negative")


@dataclass(frozen=True, slots=True)
class DocumentRequirement:
    type: str
    title: str
    # Required only from this amount (None — at any amount).
    required_from: Money | None = None
    # Required only for these legal forms (empty — for every form).
    legal_forms: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if not _SLUG.match(self.type):
            raise invalid("required_documents.type", "bad_format", "Invalid document type")
        if not self.title.strip():
            raise invalid("required_documents.title", "missing", "Document needs a title")
        if not self.legal_forms <= set(LEGAL_FORMS):
            raise invalid("required_documents.legal_forms", "unknown", "Unknown legal form")

    def applies(self, amount: Money | None, legal_form: str | None) -> bool:
        if self.required_from is not None and (amount is None or amount < self.required_from):
            return False
        if self.legal_forms and legal_form not in self.legal_forms:
            return False
        return True


@dataclass(frozen=True, slots=True)
class ProcessingProfile:
    """How the process handles an application: its route and the amount up to
    which the decision may be taken without an underwriter."""

    workflow_code: str
    auto_decision_limit: Money

    def __post_init__(self) -> None:
        if not _SLUG.match(self.workflow_code):
            raise invalid("workflow_code", "bad_format", "Invalid workflow code")
        if self.auto_decision_limit.is_negative:
            raise invalid("auto_decision_limit", "negative", "Limit can't be negative")

    def requires_manual_review(self, amount: Money) -> bool:
        return amount > self.auto_decision_limit


@dataclass(frozen=True, slots=True)
class BorrowerProfile:
    """What products need to know about a company, built from the clients snapshot."""

    legal_form: str
    business_age_months: int
    annual_revenue: Money | None
    okved_main: str
    verified: bool = True
    registry_status: str = "active"
    # The snapshot has no MSP registry data: None — checked during the review.
    in_msp_registry: bool | None = None
    # Cash gap forecast from scoring; None — unknown.
    cash_gap_expected: bool | None = None

    @property
    def okved_class(self) -> str:
        """`62.01` -> `62`."""
        return self.okved_main.split(".", 1)[0]


@dataclass(frozen=True, slots=True)
class EligibilityReason:
    code: str
    passed: bool
    message: str


@dataclass(frozen=True, slots=True)
class EligibilityCheck:
    product_code: str
    reasons: tuple[EligibilityReason, ...]

    @property
    def eligible(self) -> bool:
        return all(reason.passed for reason in self.reasons)

    @property
    def failed(self) -> tuple[EligibilityReason, ...]:
        return tuple(reason for reason in self.reasons if not reason.passed)


@dataclass(frozen=True, slots=True)
class LoanNeed:
    """What the client wants: the input of product matching."""

    purpose: str
    amount: Money
    term_months: int

    def __post_init__(self) -> None:
        if self.purpose not in PURPOSES:
            raise invalid("purpose", "unknown", "Unknown credit purpose")
        if not self.amount.amount > 0:
            raise invalid("amount", "not_positive", "Amount must be positive")
        if not 1 <= self.term_months <= MAX_TERM_MONTHS:
            raise invalid("term_months", "out_of_range", "Term is out of range")


@dataclass(frozen=True, slots=True)
class ProductTerms:
    """Copy of the product terms for a new application; `rate.max` is what the
    client may be offered (capped by a support program)."""

    code: str
    version: int
    amount: AmountRange
    term: TermRange
    rate: RateRange
    repayment_options: tuple[str, ...]
    facility: str
    collateral_required: bool
    collateral_required_from: Money | None
    required_documents: tuple[DocumentRequirement, ...]
    application_fields_schema: Mapping[str, Any]
    workflow_code: str
    auto_decision_limit: Money
