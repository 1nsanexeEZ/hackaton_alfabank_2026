"""Decision contract. The full decision (rule trace, reason codes) is for the
bank only; the client view never carries them."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Protocol
from uuid import UUID

from src.core.messaging.contracts.decision import Outcome


@dataclass(frozen=True, slots=True)
class DecisionTermsDTO:
    amount: Decimal
    term_months: int
    rate: Decimal
    monthly_payment: Decimal
    schedule_type: str
    conditions: tuple[str, ...]
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class RequestedInfoDTO:
    fields: tuple[str, ...]
    documents: tuple[str, ...]
    comment: str


@dataclass(frozen=True, slots=True)
class RuleTraceDTO:
    rule: str
    matched: bool
    detail: str


@dataclass(frozen=True, slots=True)
class LimitsDTO:
    by_revenue: Decimal | None
    by_ltv: Decimal | None
    by_capacity: Decimal | None
    # policy_v3: the limit is the minimum of every constraint, `binding` names it.
    by_product: Decimal | None = None
    by_turnover: Decimal | None = None
    by_grade: Decimal | None = None
    by_group: Decimal | None = None
    final: Decimal | None = None
    binding: str | None = None


@dataclass(frozen=True, slots=True)
class TriggerDTO:
    """A soft trigger (policy_v3): not a refusal, a reason for a person to look."""

    code: str  # tax_arrears | head_change | turnover_spike
    detail: str


@dataclass(frozen=True, slots=True)
class RateBreakdownDTO:
    """policy_v3 rate in percent a year: funding + expected loss + capital + margin;
    `total` is the rate within the product's corridor."""

    funding: Decimal
    expected_loss: Decimal
    capital: Decimal
    margin: Decimal
    total: Decimal


@dataclass(frozen=True, slots=True)
class DecisionDTO:
    id: UUID
    application_id: UUID
    policy_version: str
    key_rate: Decimal
    outcome: Outcome
    terms: DecisionTermsDTO | None
    alternative_product_code: str | None
    reason_codes: tuple[str, ...]
    client_explanation: str
    improvement_hints: tuple[str, ...]
    requested_info: RequestedInfoDTO | None
    rule_trace: tuple[RuleTraceDTO, ...]
    limits: LimitsDTO
    decided_by_type: Literal["auto", "underwriter"]
    decided_by_id: UUID | None
    override_of: UUID | None
    comment: str | None
    decided_at: datetime
    triggers: tuple[TriggerDTO, ...] = ()
    rate_breakdown: RateBreakdownDTO | None = None


@dataclass(frozen=True, slots=True)
class ClientDecisionDTO:
    outcome: Outcome
    terms: DecisionTermsDTO | None
    alternative_product_code: str | None
    client_explanation: str
    improvement_hints: tuple[str, ...]
    requested_info: RequestedInfoDTO | None


@dataclass(frozen=True, slots=True)
class PreApprovedOfferDTO:
    product_code: str
    max_amount: Decimal
    rate_from: Decimal
    term_max_months: int
    valid_until: date
    basis: str


@dataclass(frozen=True, slots=True)
class PrescreenReasonDTO:
    code: str
    passed: bool
    message: str  # shown to the client


@dataclass(frozen=True, slots=True)
class FounderPrescreenDTO:
    """The startup founder's prescreen by their own credit history."""

    status: Literal["passed", "failed"]
    founder_account_id: UUID
    founder_name: str
    checked_at: datetime
    valid_until: datetime
    # False — expired: a STARTUP application needs a new prescreen.
    valid: bool
    reasons: tuple[PrescreenReasonDTO, ...]


class DecisionFacade(Protocol):
    async def get_decision(self, application_id: UUID) -> DecisionDTO | None:
        """Back office only: includes rule_trace and reason codes."""
        ...

    async def get_client_view(self, application_id: UUID) -> ClientDecisionDTO | None: ...

    async def get_pre_approved(self, organization_id: UUID) -> list[PreApprovedOfferDTO]: ...

    async def get_founder_prescreen(self, organization_id: UUID) -> FounderPrescreenDTO | None:
        """The latest prescreen of the company's founder; None — not run yet."""
        ...
