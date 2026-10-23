import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal, Self
from uuid import UUID

from src.core.domain import Money
from src.core.exceptions.exceptions import ValidationError
from src.modules.applications.domain.fields_schema import ProductFieldsSchema

PURPOSES: frozenset[str] = frozenset(
    {
        "working_capital",
        "cash_gap",
        "equipment",
        "vehicles",
        "real_estate",
        "contract_execution",
        "refinancing",
        "expansion",
    }
)
COLLATERAL_TYPES: frozenset[str] = frozenset({"real_estate", "equipment", "vehicle", "goods"})
MAX_COMMENT_LENGTH = 500


def _invalid(field_name: str, code: str, message: str) -> ValidationError:
    return ValidationError(message, details={"field": field_name, "code": code})


def _require_aware(moment: datetime, name: str) -> None:
    if moment.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class ApplicationNumber:
    """`КР-2026-000123`: year of creation and a database sequence value."""

    value: str

    _PATTERN = re.compile(r"^КР-\d{4}-\d{6}$")

    def __post_init__(self) -> None:
        if not self._PATTERN.match(self.value):
            raise ValueError(f"Invalid application number {self.value!r}")

    @classmethod
    def issue(cls, year: int, sequence: int) -> Self:
        if not 0 < sequence < 1_000_000:
            raise ValueError("Application number sequence is exhausted")
        return cls(f"КР-{year:04d}-{sequence:06d}")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class LoanRequest:
    """What the client asks for. In a draft any part may still be empty."""

    amount: Money | None = None
    term_months: int | None = None
    purpose: str | None = None
    purpose_comment: str | None = None

    def __post_init__(self) -> None:
        if self.amount is not None and not self.amount.amount > 0:
            raise _invalid("request.amount", "not_positive", "Amount must be positive")
        if self.term_months is not None and self.term_months < 1:
            raise _invalid("request.term_months", "not_positive", "Term must be at least 1 month")
        if self.purpose is not None and self.purpose not in PURPOSES:
            raise _invalid("request.purpose", "unknown", "Unknown credit purpose")
        if self.purpose_comment is not None and len(self.purpose_comment) > MAX_COMMENT_LENGTH:
            raise _invalid("request.purpose_comment", "too_long", "Comment is too long")

    @property
    def is_complete(self) -> bool:
        return None not in (self.amount, self.term_months, self.purpose)

    def missing_fields(self) -> list[str]:
        return [
            f"request.{name}"
            for name in ("amount", "term_months", "purpose")
            if getattr(self, name) is None
        ]


@dataclass(frozen=True, slots=True)
class DocumentRequirement:
    type: str
    title: str
    # Required only from this amount (None — always).
    required_from_amount: Money | None = None
    # Required only for these legal forms (empty — for every form).
    legal_forms: frozenset[str] = frozenset()

    def applies(self, amount: Money | None, legal_form: str | None) -> bool:
        if self.required_from_amount is not None and (
            amount is None or amount < self.required_from_amount
        ):
            return False
        if self.legal_forms and legal_form not in self.legal_forms:
            return False
        return True


@dataclass(frozen=True, slots=True)
class ProductTerms:
    """Copy of the product terms taken when the draft is created: later
    changes of the catalog do not touch an application in progress."""

    code: str
    version: int
    amount_min: Money
    amount_max: Money
    term_min_months: int
    term_max_months: int
    rate_base: Decimal
    rate_max: Decimal
    repayment_options: tuple[str, ...]
    facility: str
    collateral_required: bool
    collateral_required_from: Money | None
    required_documents: tuple[DocumentRequirement, ...]
    fields_schema: ProductFieldsSchema
    workflow_code: str
    auto_decision_limit: Money

    def needs_collateral(self, amount: Money | None) -> bool:
        if self.collateral_required:
            return True
        return (
            self.collateral_required_from is not None
            and amount is not None
            and amount >= self.collateral_required_from
        )

    def documents_for(self, amount: Money | None, legal_form: str | None) -> list[str]:
        return [r.type for r in self.required_documents if r.applies(amount, legal_form)]


@dataclass(frozen=True, slots=True)
class CollateralDeclaration:
    type: str
    description: str
    declared_value: Money
    owner: Literal["self", "third_party"]

    def __post_init__(self) -> None:
        if self.type not in COLLATERAL_TYPES:
            raise _invalid("collateral.type", "unknown", "Unknown collateral type")
        if not self.description.strip() or len(self.description) > 1000:
            raise _invalid("collateral.description", "invalid", "Describe the collateral")
        if not self.declared_value.amount > 0:
            raise _invalid("collateral.declared_value", "not_positive", "Value must be positive")
        if self.owner not in ("self", "third_party"):
            raise _invalid("collateral.owner", "unknown", "Unknown collateral owner")


@dataclass(frozen=True, slots=True)
class Consents:
    """Personal data processing and credit bureau request (218-FZ): without
    both the application cannot be submitted. A decision made solely by automated
    processing (152-FZ art. 16) is optional: without it an adverse decision on an
    entrepreneur goes to a person."""

    personal_data_at: datetime | None = None
    credit_bureau_at: datetime | None = None
    given_by: UUID | None = None
    automated_decision_at: datetime | None = None

    @property
    def complete(self) -> bool:
        return self.personal_data_at is not None and self.credit_bureau_at is not None


@dataclass(frozen=True, slots=True)
class OrganizationSnapshot:
    """Company data at the moment of submission. The aggregate needs only a
    few fields; `data` keeps the whole snapshot for scoring and audit."""

    organization_id: UUID
    legal_form: str
    taken_at: datetime
    data: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_aware(self.taken_at, "taken_at")


@dataclass(frozen=True, slots=True)
class Offer:
    kind: Literal["as_requested", "counter"]
    amount: Money
    term_months: int
    rate: Decimal
    monthly_payment: Money
    schedule_type: str
    conditions: tuple[str, ...]
    expires_at: datetime
    decision_id: UUID

    def __post_init__(self) -> None:
        if not self.amount.amount > 0 or self.term_months < 1 or self.rate < 0:
            raise ValueError("Offer terms are invalid")
        _require_aware(self.expires_at, "expires_at")

    def is_expired(self, now: datetime) -> bool:
        return now >= self.expires_at

    def fingerprint(self) -> str:
        """Hash of what exactly the client signs."""
        canonical = json.dumps(
            {
                "kind": self.kind,
                "amount": str(self.amount.amount),
                "currency": self.amount.currency,
                "term_months": self.term_months,
                "rate": str(self.rate),
                "monthly_payment": str(self.monthly_payment.amount),
                "schedule_type": self.schedule_type,
                "conditions": list(self.conditions),
                "expires_at": self.expires_at.isoformat(),
                "decision_id": str(self.decision_id),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class DecisionSummary:
    """What the client sees about the decision: no reason codes, no score."""

    outcome: str
    client_explanation: str
    improvement_hints: tuple[str, ...] = ()
    alternative_product_code: str | None = None


@dataclass(frozen=True, slots=True)
class Actor:
    kind: Literal["client", "process", "system"]
    account_id: UUID | None = None

    @classmethod
    def client(cls, account_id: UUID) -> Self:
        return cls("client", account_id)


PROCESS = Actor("process")
SYSTEM = Actor("system")


@dataclass(frozen=True, slots=True)
class StatusChange:
    from_status: str | None
    to_status: str
    at: datetime
    actor: Actor
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class Signature:
    signed_by: UUID
    signed_at: datetime
    offer_hash: str
    # Filled in after the document flow answers; None right after signing.
    edo_document_id: str | None = None


@dataclass(frozen=True, slots=True)
class Disbursement:
    """The credit is paid out by the core banking system (a mock in the case)."""

    reference: str
    disbursed_at: datetime
    simulated: bool


@dataclass(frozen=True, slots=True)
class Violation:
    """One unmet condition of submission, also used for "what is left" hints."""

    code: str
    field: str
    params: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "field": self.field, **dict(self.params)}
