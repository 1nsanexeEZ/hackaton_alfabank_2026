"""Decision contract. The full decision (rule trace, reason codes) is for the
bank only; the client view never carries them."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Protocol
from uuid import UUID

from src.core.messaging.contracts.decision import Outcome

# A manual review comes in two kinds. check — the data and the models look fine
# or the risk is moderate, but a person has to look: soft triggers, an amount
# above the automatic limit, both models in the yellow zone. dispute — the
# models disagree or the data cannot be trusted: the underwriter decides it all.
ReviewKind = Literal["check", "dispute"]
DISPUTE_REASON_CODES: frozenset[str] = frozenset(
    {
        "ROUTE_MODELS_DISAGREE",
        "ROUTE_ML_UNAVAILABLE",
        "ROUTE_SOURCES_FAILED",
        "ROUTE_VERIFICATION_MISMATCH",
        "ROUTE_MASS_ADDRESS",
        "ROUTE_REVENUE_MISMATCH",
        # policy_v6: проверки по 115-ФЗ нет — данным нельзя доверять.
        "ROUTE_AML_INCOMPLETE",
        # policy_v8: о третьих лицах клиент не сказал — данных не хватает.
        "ROUTE_THIRD_PARTIES_UNKNOWN",
    }
)


def review_kind(outcome: str, reason_codes: Iterable[str]) -> ReviewKind | None:
    """The kind of a manual review by its reason codes; None unless MANUAL_REVIEW."""
    if outcome != "MANUAL_REVIEW":
        return None
    return "dispute" if any(c in DISPUTE_REASON_CODES for c in reason_codes) else "check"


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
    # MANUAL_REVIEW only: check or dispute (`review_kind`); None otherwise.
    review: ReviewKind | None = None


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


@dataclass(frozen=True, slots=True)
class ProjectCheckDTO:
    code: str  # founder_prescreen | industry | dscr | own_funds | coverage | product_amount
    passed: bool
    message: str  # shown to the client, no thresholds


@dataclass(frozen=True, slots=True)
class ProjectFiguresDTO:
    """Bank only: the request, the payment terms it was counted on and the figures of the
    financial model at the requested amount."""

    requested_amount: Decimal
    term_months: int
    rate: Decimal  # the top of the product's corridor
    cash_flow: Decimal  # revenue − expenses over the horizon of the model
    debt_service: Decimal  # loan payments over the same horizon
    dscr: Decimal | None
    own_share: Decimal
    coverage: Decimal
    capacity: Decimal  # what the project carries by scoring, before the product's limits


@dataclass(frozen=True, slots=True)
class ProjectAssessmentDTO:
    """A startup's project assessment by its business plan: passed — a pre-approved offer of
    `product_code` up to `max_amount`."""

    status: Literal["passed", "failed"]
    product_code: str
    plan_revision: int
    max_amount: Decimal | None
    checked_at: datetime
    valid_until: datetime
    # False — expired: run a new one.
    valid: bool
    reasons: tuple[ProjectCheckDTO, ...]
    figures: ProjectFiguresDTO
    version: str


class DecisionFacade(Protocol):
    async def get_decision(self, application_id: UUID) -> DecisionDTO | None:
        """Back office only: includes rule_trace and reason codes."""
        ...

    async def get_client_view(self, application_id: UUID) -> ClientDecisionDTO | None: ...

    async def get_pre_approved(self, organization_id: UUID) -> list[PreApprovedOfferDTO]: ...

    async def get_founder_prescreen(self, organization_id: UUID) -> FounderPrescreenDTO | None:
        """The latest prescreen of the company's founder; None — not run yet."""
        ...

    async def get_project_assessment(self, organization_id: UUID) -> ProjectAssessmentDTO | None:
        """The latest project assessment of a startup; None — not run yet."""
        ...
