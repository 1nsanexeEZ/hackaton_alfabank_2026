"""Правила policy_v5: две модели вместо матрицы грейд × сумма. Зона PD-модели и зона ML-модели
по матрице дают вердикт — одобрение (дальше лимиты), проверка, спорная или отказ; стоп-факторы,
дозапрос выручки, расхождения в данных, мягкие триггеры и лимит автоматики — поверх матрицы.
Пороги — из `policy_v5.yaml`; базовая заявка (обе модели в зелёной зоне) одобряется как просили."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from typing import Any

import pytest

from src.modules.decision.domain.model import (
    BureauInput,
    DecisionInput,
    PolicyDecision,
    ReasonCode,
    RequestInput,
    ScoreInput,
)
from src.modules.decision.facade import review_kind
from src.modules.decision.infrastructure.config_loader import load_policy
from tests.decision.unit.test_credit_policy_rules import company
from tests.decision.unit.test_credit_policy_v3_rules import WIDE, hit, v3
from tests.decision.unit.test_credit_policy_v4_rules import startup

POLICY = load_policy("policy_v5")
KEY_RATE = POLICY.config.key_rate_reference
# Грейд и PD каждой зоны: зелёная A–D, жёлтая E–G, красная H–J.
ZONE = {"green": ("B", "0.0080"), "yellow": ("E", "0.0310"), "red": ("H", "0.1200")}


def models(pd_zone: str = "green", ml_zone: str | None = "green", **flags: Any) -> ScoreInput:
    grade, pd = ZONE[pd_zone]
    ml_grade, ml_pd = ZONE[ml_zone] if ml_zone is not None else (None, None)
    return ScoreInput(
        score=700,
        grade=grade,  # type: ignore[arg-type]
        flags=frozenset(flags.get("flags", ())),
        pd_12m=Decimal(pd),
        ml_grade=ml_grade,  # type: ignore[arg-type]
        ml_pd_12m=Decimal(ml_pd) if ml_pd is not None else None,
    )


def v5(**overrides: Any) -> DecisionInput:
    """Заявка без замечаний, обе модели в зелёной зоне, автоматика продукта до 30 млн."""
    return v3(**{"product": WIDE, "score": models(), **overrides})


def decide(inp: DecisionInput) -> PolicyDecision:
    return POLICY.decide(inp, key_rate=KEY_RATE)


def review(decision: PolicyDecision) -> str | None:
    return review_kind(decision.outcome, decision.reason_codes)


def test_both_models_green_is_approved_in_rule_order() -> None:
    decision = decide(v5())
    assert decision.outcome == "APPROVE" and decision.policy_version == "policy_v5"
    assert decision.reason_codes == () and review(decision) is None
    groups = list(dict.fromkeys(h.rule.split(".", 1)[0] for h in decision.rule_trace))
    assert groups == [
        "stop",
        "info",
        "pricing",
        "limits",
        "route",
        "trigger",
        "strategy",
        "cash_gap",
        "outcome",
        "offer",
    ]
    rule = hit(decision, "strategy.two_models")
    assert not rule.matched
    assert rule.detail == (
        "PD-модель: грейд B (PD 0.80%) — зелёная; ML-модель: грейд B (PD 0.80%) — зелёная → "
        "одобрение, дальше лимиты"
    )
    assert "strategy.risk_matrix" not in {h.rule for h in decision.rule_trace}


@pytest.mark.parametrize(
    ("pd_zone", "ml_zone", "outcome", "reason", "kind"),
    [
        ("green", "green", "APPROVE", None, None),
        ("green", "yellow", "MANUAL_REVIEW", ReasonCode.ROUTE_MODELS_CHECK, "check"),
        ("green", "red", "MANUAL_REVIEW", ReasonCode.ROUTE_MODELS_DISAGREE, "dispute"),
        ("yellow", "green", "MANUAL_REVIEW", ReasonCode.ROUTE_MODELS_CHECK, "check"),
        ("yellow", "yellow", "MANUAL_REVIEW", ReasonCode.ROUTE_MODELS_CHECK, "check"),
        ("yellow", "red", "MANUAL_REVIEW", ReasonCode.ROUTE_MODELS_DISAGREE, "dispute"),
        ("red", "green", "MANUAL_REVIEW", ReasonCode.ROUTE_MODELS_DISAGREE, "dispute"),
        ("red", "yellow", "MANUAL_REVIEW", ReasonCode.ROUTE_MODELS_DISAGREE, "dispute"),
        ("red", "red", "REJECT", ReasonCode.STOP_MODELS_HIGH_RISK, None),
    ],
)
def test_matrix_of_the_two_models(
    pd_zone: str, ml_zone: str, outcome: str, reason: ReasonCode | None, kind: str | None
) -> None:
    decision = decide(v5(score=models(pd_zone, ml_zone)))
    assert decision.outcome == outcome
    assert decision.reason_codes == ((reason,) if reason is not None else ())
    assert review(decision) == kind
    assert hit(decision, "strategy.two_models").matched is (reason is not None)


def test_without_the_ml_estimate_the_application_is_disputed() -> None:
    decision = decide(v5(score=models("green", None)))
    assert decision.outcome == "MANUAL_REVIEW"
    assert decision.reason_codes == (ReasonCode.ROUTE_ML_UNAVAILABLE,)
    assert review(decision) == "dispute"
    assert hit(decision, "strategy.two_models").detail == (
        "PD-модель: грейд B (PD 0.80%) — зелёная; оценки ML-модели нет → "
        "спорная заявка — решает андеррайтер"
    )


def test_both_red_on_incomplete_data_goes_to_a_person() -> None:
    decision = decide(v5(score=models("red", "red"), sources_failed=("kontur",)))
    assert decision.outcome == "MANUAL_REVIEW"
    assert decision.reason_codes == (ReasonCode.ROUTE_SOURCES_FAILED,)
    assert review(decision) == "dispute"


def test_soft_trigger_does_not_save_both_red_from_a_reject() -> None:
    arrears = company(tax_arrears=Decimal("1000"), account_blocks=0, head_tenure_months=60)
    decision = decide(v5(score=models("red", "red"), company=arrears))
    assert decision.outcome == "REJECT"
    assert decision.reason_codes == (ReasonCode.STOP_MODELS_HIGH_RISK,)


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        (
            {"company": company(tax_arrears=Decimal("1000"), account_blocks=0)},
            ReasonCode.ROUTE_SOFT_TRIGGER,
        ),
        (
            {
                "request": RequestInput(Decimal("6000000"), 24),
                "product": replace(WIDE, auto_decision_limit=Decimal("5000000")),
            },
            ReasonCode.ROUTE_AMOUNT_OVER_AUTO_LIMIT,
        ),
    ],
)
def test_small_suspicion_on_green_models_is_a_check(
    overrides: dict[str, Any], reason: ReasonCode
) -> None:
    decision = decide(v5(**overrides))
    assert decision.outcome == "MANUAL_REVIEW"
    assert decision.reason_codes == (reason,)
    assert review(decision) == "check"


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"sources_failed": ("kontur",)}, ReasonCode.ROUTE_SOURCES_FAILED),
        (
            {"score": models(flags=("verification_mismatch",))},
            ReasonCode.ROUTE_VERIFICATION_MISMATCH,
        ),
        (
            {"score": models(flags=("revenue_mismatch",)), "revenue_info_requested": True},
            ReasonCode.ROUTE_REVENUE_MISMATCH,
        ),
        (
            {"company": company(mass_address=True, tax_arrears=Decimal(0), account_blocks=0)},
            None,  # массовый адрес в policy_v5 — стоп-фактор, как в v4
        ),
    ],
)
def test_data_problems_on_green_models_make_a_dispute(
    overrides: dict[str, Any], reason: ReasonCode | None
) -> None:
    decision = decide(v5(**overrides))
    if reason is None:
        assert decision.outcome == "REJECT"
        assert decision.reason_codes == (ReasonCode.STOP_MASS_ADDRESS,)
        return
    assert decision.outcome == "MANUAL_REVIEW"
    assert decision.reason_codes == (reason,)
    assert review(decision) == "dispute"


def test_stop_factors_reject_before_the_models() -> None:
    decision = decide(v5(bureau=BureauInput(True, 120, Decimal("180000"))))
    assert decision.outcome == "REJECT"
    assert ReasonCode.STOP_OVERDUE_90 in decision.reason_codes
    assert "strategy.two_models" not in {h.rule for h in decision.rule_trace}


def test_unconfirmed_revenue_is_requested_before_the_models() -> None:
    decision = decide(v5(score=models("green", "red", flags=("revenue_mismatch",))))
    assert decision.outcome == "REQUEST_INFO"
    assert decision.reason_codes == (ReasonCode.INFO_REVENUE_NOT_CONFIRMED,)


def test_approve_still_goes_through_the_limits() -> None:
    decision = decide(v5(request=RequestInput(Decimal("29000000"), 24)))
    assert decision.outcome == "COUNTER_OFFER"
    assert decision.terms is not None and decision.terms.amount < Decimal("29000000")


def test_startup_product_skips_the_models() -> None:
    decision = POLICY.decide(
        replace(startup("passed"), score=models("red", "red")), key_rate=KEY_RATE
    )
    assert decision.outcome == "MANUAL_REVIEW"
    assert decision.reason_codes == (ReasonCode.ROUTE_AMOUNT_OVER_AUTO_LIMIT,)
    rule = hit(decision, "strategy.two_models")
    assert not rule.matched and "проектная оценка" in rule.detail


def test_earlier_versions_ignore_the_ml_estimate() -> None:
    decision = load_policy("policy_v4").decide(v5(score=models("green", "red")), key_rate=KEY_RATE)
    assert decision.outcome == "APPROVE"
    assert "strategy.two_models" not in {h.rule for h in decision.rule_trace}


def test_v5_is_v4_with_two_models_instead_of_the_matrix() -> None:
    v4, v5_config = load_policy("policy_v4").config, POLICY.config
    assert v5_config.risk_matrix == () and v4.model_matrix == {}
    assert len(v5_config.model_matrix) == 9 and set(v5_config.model_zones) == set("ABCDEFGHIJ")
    same = replace(
        v5_config, version=v4.version, risk_matrix=v4.risk_matrix, model_zones={}, model_matrix={}
    )
    assert same == v4


@pytest.mark.parametrize(
    ("outcome", "codes", "kind"),
    [
        ("APPROVE", (), None),
        ("REJECT", ("STOP_MODELS_HIGH_RISK",), None),
        ("MANUAL_REVIEW", ("ROUTE_SOFT_TRIGGER", "ROUTE_MODELS_CHECK"), "check"),
        ("MANUAL_REVIEW", ("ROUTE_AMOUNT_OVER_AUTO_LIMIT", "ROUTE_REVENUE_MISMATCH"), "dispute"),
        ("MANUAL_REVIEW", ("ROUTE_RISK_MATRIX",), "check"),
    ],
)
def test_review_kind_by_reason_codes(
    outcome: str, codes: tuple[str, ...], kind: str | None
) -> None:
    assert review_kind(outcome, codes) == kind
