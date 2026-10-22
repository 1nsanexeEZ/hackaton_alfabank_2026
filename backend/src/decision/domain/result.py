"""DecisionResult — неизменяемый итог решения по заявке.

Автоматическое решение и ручное решение андеррайтера — разные записи: ручное ссылается на
переопределённое через `override_of`, авторешение не удаляется (аудит).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Literal
from uuid import UUID

from src.decision.domain.model import InfoNeed, Limits, Outcome, PolicyDecision, RuleHit

DecidedByType = Literal["auto", "underwriter"]


@dataclass(frozen=True, slots=True)
class DecisionInputRefs:
    """На чём принято решение: ссылки на результат скоринга, снимок и версию продукта."""

    scoring_result_id: UUID | None
    enrichment_snapshot_id: UUID | None
    product_code: str
    product_version: int


@dataclass(frozen=True, slots=True)
class ApprovedTerms:
    amount: Decimal
    term_months: int
    rate: Decimal
    schedule_type: str
    monthly_payment: Decimal
    conditions: tuple[str, ...]
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class DecisionResult:
    id: UUID
    application_id: UUID
    requested_by_command: UUID
    policy_version: str
    key_rate: Decimal
    inputs: DecisionInputRefs
    outcome: Outcome
    terms: ApprovedTerms | None
    alternative_product_code: str | None
    reason_codes: tuple[str, ...]
    client_explanation: str
    improvement_hints: tuple[str, ...]
    requested_info: InfoNeed | None
    rule_trace: tuple[RuleHit, ...]
    limits: Limits
    decided_by_type: DecidedByType
    decided_by_id: UUID | None
    override_of: UUID | None
    comment: str | None
    decided_at: datetime


def automatic_result(
    decision: PolicyDecision,
    *,
    result_id: UUID,
    application_id: UUID,
    command_event_id: UUID,
    inputs: DecisionInputRefs,
    monthly_payment: Decimal | None,
    offer_valid_days: int,
    now: datetime,
) -> DecisionResult:
    """Итог политики → запись решения; платёж оффера считает products (одна формула)."""
    terms = None
    if decision.terms is not None:
        offer = decision.terms
        terms = ApprovedTerms(
            amount=offer.amount,
            term_months=offer.term_months,
            rate=offer.rate,
            schedule_type=offer.schedule_type,
            monthly_payment=monthly_payment if monthly_payment is not None else Decimal(0),
            conditions=offer.conditions,
            expires_at=now + timedelta(days=offer_valid_days),
        )
    return DecisionResult(
        id=result_id,
        application_id=application_id,
        requested_by_command=command_event_id,
        policy_version=decision.policy_version,
        key_rate=decision.key_rate,
        inputs=inputs,
        outcome=decision.outcome,
        terms=terms,
        alternative_product_code=decision.alternative_product_code,
        reason_codes=tuple(str(code) for code in decision.reason_codes),
        client_explanation=decision.client_explanation,
        improvement_hints=decision.improvement_hints,
        requested_info=decision.requested_info,
        rule_trace=decision.rule_trace,
        limits=decision.limits,
        decided_by_type="auto",
        decided_by_id=None,
        override_of=None,
        comment=None,
        decided_at=now,
    )
