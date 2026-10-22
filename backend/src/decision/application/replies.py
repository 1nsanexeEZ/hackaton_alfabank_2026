"""Ответ `DecisionMade` из сохранённого решения — один для автоматического и ручного.

Оффер уходит только у APPROVE и COUNTER_OFFER: «как просили» для одобрения, иначе встречное.
График платежей в контракте — annuity, differentiated или interest_only; другие виды графика
продукта (по графику контракта) предлагаются как аннуитет.
"""

from __future__ import annotations

from typing import Literal, cast
from uuid import UUID

from src.core.messaging.contracts.applications import OfferTerms
from src.core.messaging.contracts.decision import DecisionMade, RequestedInfo
from src.core.messaging.outbox import OutboxWriter
from src.decision.domain.result import DecisionResult

ScheduleType = Literal["annuity", "differentiated", "interest_only"]
SCHEDULE_TYPES: frozenset[str] = frozenset({"annuity", "differentiated", "interest_only"})
OFFER_OUTCOMES: frozenset[str] = frozenset({"APPROVE", "COUNTER_OFFER"})


def offer_schedule(schedule_type: str) -> ScheduleType:
    return cast(ScheduleType, schedule_type if schedule_type in SCHEDULE_TYPES else "annuity")


def decision_made(result: DecisionResult) -> DecisionMade:
    offer = None
    if result.terms is not None and result.outcome in OFFER_OUTCOMES:
        terms = result.terms
        offer = OfferTerms(
            kind="as_requested" if result.outcome == "APPROVE" else "counter",
            amount=terms.amount,
            term_months=terms.term_months,
            rate=terms.rate,
            monthly_payment=terms.monthly_payment,
            schedule_type=offer_schedule(terms.schedule_type),
            conditions=list(terms.conditions),
            expires_at=terms.expires_at,
        )
    info = result.requested_info
    return DecisionMade(
        application_id=result.application_id,
        decision_id=result.id,
        outcome=result.outcome,
        offer=offer,
        decided_by=result.decided_by_type,
        requested_info=RequestedInfo(
            fields=list(info.fields), documents=list(info.documents), comment=info.comment
        )
        if info is not None
        else None,
        client_explanation=result.client_explanation,
        improvement_hints=list(result.improvement_hints),
        alternative_product_code=result.alternative_product_code,
    )


async def publish_decision(
    outbox: OutboxWriter, result: DecisionResult, command_event_id: UUID
) -> None:
    await outbox.add(
        decision_made(result),
        key=result.application_id,
        correlation_id=result.application_id,
        causation_id=command_event_id,
    )
