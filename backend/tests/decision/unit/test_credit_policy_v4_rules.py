"""Правила policy_v4: заявка на продукт для стартапа — только с пройденным и действующим
предскрином учредителя; матрица грейд × сумма для него не применяется, решает андеррайтер
на проектной оценке. Остальные продукты решаются как в v3."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from src.modules.decision.domain.model import DecisionInput, ReasonCode, RequestInput
from src.modules.decision.infrastructure.config_loader import load_policy
from tests.decision.unit.test_credit_policy_rules import product
from tests.decision.unit.test_credit_policy_v3_rules import hit, score, v3

POLICY = load_policy("policy_v4")
KEY_RATE = POLICY.config.key_rate_reference
STARTUP = product(
    code="STARTUP",
    amount_min=Decimal("500000"),
    amount_max=Decimal("5000000"),
    rate_base=Decimal("15"),
    rate_max=Decimal("26"),
    auto_decision_limit=Decimal(0),
)


def startup(status: str | None, **overrides: object) -> DecisionInput:
    """Молодая компания, грейд I по упрощённой карте, 3 млн на STARTUP."""
    base = v3(
        product=STARTUP,
        score=score("I", "0.17"),
        request=RequestInput(Decimal("3000000"), 36),
        founder_prescreen=status,
    )
    return replace(base, **overrides)  # type: ignore[arg-type]


def test_passed_prescreen_goes_to_the_project_assessment() -> None:
    decision = POLICY.decide(startup("passed"), key_rate=KEY_RATE)
    assert decision.outcome == "MANUAL_REVIEW"
    assert decision.reason_codes == (ReasonCode.ROUTE_AMOUNT_OVER_AUTO_LIMIT,)
    assert hit(decision, "stop.founder_prescreen").matched is False
    matrix = hit(decision, "strategy.risk_matrix")
    assert not matrix.matched and "проектная оценка" in matrix.detail


@pytest.mark.parametrize(
    ("status", "detail"),
    [
        ("failed", "предскрин учредителя не пройден"),
        ("expired", "предскрин учредителя истёк к подаче заявки"),
        ("missing", "предскрина учредителя не было"),
        (None, "предскрина учредителя не было"),
    ],
)
def test_startup_without_a_passed_prescreen_is_rejected(status: str | None, detail: str) -> None:
    decision = POLICY.decide(startup(status), key_rate=KEY_RATE)
    assert decision.outcome == "REJECT"
    assert decision.reason_codes == (ReasonCode.STOP_FOUNDER_PRESCREEN,)
    assert hit(decision, "stop.founder_prescreen").detail == detail
    assert "проверка личной кредитной истории учредителя" in decision.client_explanation


def test_other_products_are_not_asked_for_a_prescreen() -> None:
    decision = POLICY.decide(v3(), key_rate=KEY_RATE)
    assert decision.outcome == "APPROVE" and decision.policy_version == "policy_v4"
    assert "stop.founder_prescreen" not in {h.rule for h in decision.rule_trace}


def test_v3_knows_no_startup_branch() -> None:
    decision = load_policy("policy_v3").decide(startup("failed"), key_rate=KEY_RATE)
    rules = {h.rule for h in decision.rule_trace}
    assert "stop.founder_prescreen" not in rules
    assert ReasonCode.STOP_FOUNDER_PRESCREEN not in decision.reason_codes


def test_no_pre_approval_for_a_startup_product_by_the_policy_itself() -> None:
    """Предодобрение стартапу не считается совсем (pre_approval.py пропускает startup_only):
    у него нет выручки, политика и так вернула бы None."""
    from src.modules.decision.domain.model import PreApprovalInput

    offer = POLICY.pre_approve(
        PreApprovalInput(
            product=STARTUP,
            grade="I",
            score=560,
            registry_status="active",
            annual_revenue=None,
            okved_main="62.01",
        ),
        key_rate=KEY_RATE,
    )
    assert offer is None
