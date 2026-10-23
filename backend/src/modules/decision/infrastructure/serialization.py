"""JSON-части записи решения: условия, ссылки на вход, дозапрос, трасса, лимиты.

Суммы и ставки — строками (Decimal без потерь), даты — ISO; чистый stdlib.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from src.modules.decision.domain.model import InfoNeed, Limits, RateBreakdown, RuleHit, Trigger
from src.modules.decision.domain.result import ApprovedTerms, DecisionInputRefs


def dump_terms(terms: ApprovedTerms | None) -> dict[str, Any] | None:
    if terms is None:
        return None
    return {
        "amount": str(terms.amount),
        "term_months": terms.term_months,
        "rate": str(terms.rate),
        "schedule_type": terms.schedule_type,
        "monthly_payment": str(terms.monthly_payment),
        "conditions": list(terms.conditions),
        "expires_at": terms.expires_at.isoformat(),
    }


def load_terms(raw: dict[str, Any] | None) -> ApprovedTerms | None:
    if raw is None:
        return None
    return ApprovedTerms(
        amount=Decimal(raw["amount"]),
        term_months=raw["term_months"],
        rate=Decimal(raw["rate"]),
        schedule_type=raw["schedule_type"],
        monthly_payment=Decimal(raw["monthly_payment"]),
        conditions=tuple(raw["conditions"]),
        expires_at=datetime.fromisoformat(raw["expires_at"]),
    )


def dump_inputs(refs: DecisionInputRefs) -> dict[str, Any]:
    return {
        "scoring_result_id": _uuid_str(refs.scoring_result_id),
        "enrichment_snapshot_id": _uuid_str(refs.enrichment_snapshot_id),
        "product_code": refs.product_code,
        "product_version": refs.product_version,
    }


def load_inputs(raw: dict[str, Any]) -> DecisionInputRefs:
    return DecisionInputRefs(
        scoring_result_id=_uuid(raw["scoring_result_id"]),
        enrichment_snapshot_id=_uuid(raw["enrichment_snapshot_id"]),
        product_code=raw["product_code"],
        product_version=raw["product_version"],
    )


def dump_info(info: InfoNeed | None) -> dict[str, Any] | None:
    if info is None:
        return None
    return {"fields": list(info.fields), "documents": list(info.documents), "comment": info.comment}


def load_info(raw: dict[str, Any] | None) -> InfoNeed | None:
    if raw is None:
        return None
    return InfoNeed(tuple(raw["fields"]), tuple(raw["documents"]), raw["comment"])


def dump_trace(trace: tuple[RuleHit, ...]) -> list[dict[str, Any]]:
    return [{"rule": h.rule, "matched": h.matched, "detail": h.detail} for h in trace]


def load_trace(raw: list[dict[str, Any]]) -> tuple[RuleHit, ...]:
    return tuple(RuleHit(h["rule"], h["matched"], h["detail"]) for h in raw)


def dump_limits(limits: Limits) -> dict[str, Any]:
    return {
        "by_product": _dec_str(limits.by_product),
        "by_revenue": _dec_str(limits.by_revenue),
        "by_ltv": _dec_str(limits.by_ltv),
        "by_capacity": _dec_str(limits.by_capacity),
        "final": _dec_str(limits.final),
        "by_turnover": _dec_str(limits.by_turnover),
        "by_grade": _dec_str(limits.by_grade),
        "by_group": _dec_str(limits.by_group),
        "binding": limits.binding,
    }


def load_limits(raw: dict[str, Any]) -> Limits:
    """Решения до policy_v3 хранят только первые пять ключей."""
    return Limits(
        by_product=_dec(raw.get("by_product")),
        by_revenue=_dec(raw.get("by_revenue")),
        by_ltv=_dec(raw.get("by_ltv")),
        by_capacity=_dec(raw.get("by_capacity")),
        final=_dec(raw.get("final")),
        by_turnover=_dec(raw.get("by_turnover")),
        by_grade=_dec(raw.get("by_grade")),
        by_group=_dec(raw.get("by_group")),
        binding=raw.get("binding"),
    )


def dump_triggers(triggers: tuple[Trigger, ...]) -> list[dict[str, Any]]:
    return [{"code": t.code, "detail": t.detail} for t in triggers]


def load_triggers(raw: list[dict[str, Any]] | None) -> tuple[Trigger, ...]:
    return tuple(Trigger(t["code"], t["detail"]) for t in raw or ())


def dump_rate_breakdown(breakdown: RateBreakdown | None) -> dict[str, Any] | None:
    if breakdown is None:
        return None
    return {
        "funding": str(breakdown.funding),
        "expected_loss": str(breakdown.expected_loss),
        "capital": str(breakdown.capital),
        "margin": str(breakdown.margin),
        "total": str(breakdown.total),
    }


def load_rate_breakdown(raw: dict[str, Any] | None) -> RateBreakdown | None:
    if raw is None:
        return None
    return RateBreakdown(
        funding=Decimal(raw["funding"]),
        expected_loss=Decimal(raw["expected_loss"]),
        capital=Decimal(raw["capital"]),
        margin=Decimal(raw["margin"]),
        total=Decimal(raw["total"]),
    )


def _dec_str(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def _dec(value: str | None) -> Decimal | None:
    return Decimal(value) if value is not None else None


def _uuid_str(value: UUID | None) -> str | None:
    return str(value) if value is not None else None


def _uuid(value: str | None) -> UUID | None:
    return UUID(value) if value is not None else None
