"""Решение → DTO фасада. Граница раскрытия: клиентский вид собирается отдельно и не получает
`reason_codes`, `rule_trace`, лимитов и комментария андеррайтера."""

from __future__ import annotations

from datetime import datetime

from src.modules.decision.application.ports import FounderPrescreen, PreApprovedOffer
from src.modules.decision.domain.model import InfoNeed
from src.modules.decision.domain.result import ApprovedTerms, DecisionResult
from src.modules.decision.facade import (
    ClientDecisionDTO,
    DecisionDTO,
    DecisionTermsDTO,
    FounderPrescreenDTO,
    LimitsDTO,
    PreApprovedOfferDTO,
    PrescreenReasonDTO,
    RateBreakdownDTO,
    RequestedInfoDTO,
    RuleTraceDTO,
    TriggerDTO,
    review_kind,
)


def decision_dto(result: DecisionResult) -> DecisionDTO:
    return DecisionDTO(
        id=result.id,
        application_id=result.application_id,
        policy_version=result.policy_version,
        key_rate=result.key_rate,
        outcome=result.outcome,
        terms=_terms(result.terms),
        alternative_product_code=result.alternative_product_code,
        reason_codes=tuple(result.reason_codes),
        client_explanation=result.client_explanation,
        improvement_hints=tuple(result.improvement_hints),
        requested_info=_info(result.requested_info),
        rule_trace=tuple(RuleTraceDTO(h.rule, h.matched, h.detail) for h in result.rule_trace),
        limits=LimitsDTO(
            by_revenue=result.limits.by_revenue,
            by_ltv=result.limits.by_ltv,
            by_capacity=result.limits.by_capacity,
            by_product=result.limits.by_product,
            by_turnover=result.limits.by_turnover,
            by_grade=result.limits.by_grade,
            by_group=result.limits.by_group,
            final=result.limits.final,
            binding=result.limits.binding,
        ),
        decided_by_type=result.decided_by_type,
        decided_by_id=result.decided_by_id,
        override_of=result.override_of,
        comment=result.comment,
        decided_at=result.decided_at,
        triggers=tuple(TriggerDTO(t.code, t.detail) for t in result.triggers),
        rate_breakdown=RateBreakdownDTO(
            funding=result.rate_breakdown.funding,
            expected_loss=result.rate_breakdown.expected_loss,
            capital=result.rate_breakdown.capital,
            margin=result.rate_breakdown.margin,
            total=result.rate_breakdown.total,
        )
        if result.rate_breakdown is not None
        else None,
        review=review_kind(result.outcome, result.reason_codes),
    )


def client_decision_dto(result: DecisionResult) -> ClientDecisionDTO:
    return ClientDecisionDTO(
        outcome=result.outcome,
        terms=_terms(result.terms),
        alternative_product_code=result.alternative_product_code,
        client_explanation=result.client_explanation,
        improvement_hints=tuple(result.improvement_hints),
        requested_info=_info(result.requested_info),
    )


def pre_approved_dto(offer: PreApprovedOffer) -> PreApprovedOfferDTO:
    return PreApprovedOfferDTO(
        product_code=offer.product_code,
        max_amount=offer.max_amount,
        rate_from=offer.rate_from,
        term_max_months=offer.term_max_months,
        valid_until=offer.valid_until,
        basis=offer.basis,
    )


def prescreen_dto(prescreen: FounderPrescreen, now: datetime) -> FounderPrescreenDTO:
    return FounderPrescreenDTO(
        status=prescreen.status,
        founder_account_id=prescreen.founder_account_id,
        founder_name=prescreen.founder_name,
        checked_at=prescreen.checked_at,
        valid_until=prescreen.valid_until,
        valid=prescreen.valid_at(now),
        reasons=tuple(PrescreenReasonDTO(r.code, r.passed, r.message) for r in prescreen.reasons),
    )


def _terms(terms: ApprovedTerms | None) -> DecisionTermsDTO | None:
    if terms is None:
        return None
    return DecisionTermsDTO(
        amount=terms.amount,
        term_months=terms.term_months,
        rate=terms.rate,
        monthly_payment=terms.monthly_payment,
        schedule_type=terms.schedule_type,
        conditions=tuple(terms.conditions),
        expires_at=terms.expires_at,
    )


def _info(info: InfoNeed | None) -> RequestedInfoDTO | None:
    if info is None:
        return None
    return RequestedInfoDTO(
        fields=tuple(info.fields), documents=tuple(info.documents), comment=info.comment
    )
