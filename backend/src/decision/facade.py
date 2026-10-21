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


class DecisionFacade(Protocol):
    async def get_decision(self, application_id: UUID) -> DecisionDTO | None:
        """Back office only: includes rule_trace and reason codes."""
        ...

    async def get_client_view(self, application_id: UUID) -> ClientDecisionDTO | None: ...

    async def get_pre_approved(self, organization_id: UUID) -> list[PreApprovedOfferDTO]: ...
