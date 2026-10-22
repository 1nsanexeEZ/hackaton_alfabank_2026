"""Правила policy_v3 по одному: мягкие триггеры, матрица грейд × сумма, лимит как минимум из
ограничений, ставка из компонент, поручительство, шкала A–J и предодобрение. Пороги — из
`policy_v3.yaml`; базовая заявка (грейд A, PD 0,41%) одобряется как просили."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from typing import Any

import pytest

from src.modules.decision.domain.model import (
    LEGACY_SCALE,
    PD_SCALE,
    AccountingInput,
    BureauInput,
    CashflowInput,
    CollateralInput,
    CounterpartyInput,
    DecisionInput,
    HeadBureauInput,
    PolicyDecision,
    PreApprovalInput,
    ReasonCode,
    RequestInput,
    RuleHit,
    ScoreInput,
    on_scale,
)
from src.modules.decision.infrastructure.config_loader import load_policy
from tests.decision.unit.test_credit_policy_rules import company, make, product, secured

POLICY = load_policy("policy_v3")
KEY_RATE = POLICY.config.key_rate_reference
CLEAN = CounterpartyInput(0, Decimal(0), Decimal(0))
# Автоматика продукта — до 30 млн, чтобы сумму к человеку направляла только матрица.
WIDE = product(auto_decision_limit=Decimal("30000000"))


def score(grade: str = "A", pd: str | None = "0.0041") -> ScoreInput:
    return ScoreInput(
        score=800,
        grade=grade,  # type: ignore[arg-type]
        flags=frozenset(),
        pd_12m=Decimal(pd) if pd is not None else None,
    )


def v3(**overrides: Any) -> DecisionInput:
    """Заявка без замечаний: все источники ответили, руководитель не менялся."""
    base = make(
        company=company(
            tax_arrears=Decimal(0),
            account_blocks=0,
            head_tenure_months=60,
            head_since_registration=True,
        ),
        score=score(),
        bureau=BureauInput(
            True, 0, Decimal("180000"), current_overdue_days=0, debt_balance=Decimal("3000000")
        ),
        counterparty=CLEAN,
        accounting=AccountingInput(2025, Decimal("48000000"), Decimal("12600000")),
        head_bureau=HeadBureauInput("ok", 0),
    )
    return replace(base, **overrides)


def statement(*inflows: str, net: str = "500000") -> CashflowInput:
    values = tuple(Decimal(v) for v in inflows)
    return CashflowInput(
        average_monthly_net=Decimal(net),
        gap_detected=False,
        gap_month=None,
        revenue_confirmed=True,
        monthly_inflows=values,
        annual_inflow=sum(values, Decimal(0)),
    )


def decide(inp: DecisionInput) -> PolicyDecision:
    return POLICY.decide(inp, key_rate=KEY_RATE)


def hit(decision: PolicyDecision, rule: str) -> RuleHit:
    return next(h for h in decision.rule_trace if h.rule == rule)


def test_clean_application_is_approved_in_rule_order() -> None:
    decision = decide(v3())
    assert decision.outcome == "APPROVE" and decision.policy_version == "policy_v3"
    assert decision.triggers == () and decision.reason_codes == ()
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
    # Грейд отсекает матрица: ни стоп-фактора, ни маршрута по грейду.
    rules = {h.rule for h in decision.rule_trace}
    assert not rules & {"stop.grade", "route.grade", "route.tax_arrears"}


def test_earlier_versions_do_not_get_v3_rules() -> None:
    decision = load_policy("policy_v2").decide(v3(score=score("A", None)), key_rate=KEY_RATE)
    groups = {h.rule.split(".", 1)[0] for h in decision.rule_trace}
    assert not groups & {"trigger", "strategy", "offer"}
    assert decision.rate_breakdown is None and decision.limits.binding is None


# --- мягкие триггеры ---


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        (
            {
                "company": company(
                    tax_arrears=Decimal("1000"), account_blocks=0, head_tenure_months=60
                )
            },
            "tax_arrears",
        ),
        (
            {"company": company(tax_arrears=Decimal(0), account_blocks=0, head_tenure_months=3)},
            "head_change",
        ),
        (
            {"cashflow": statement(*["1000000"] * 9, "2000000", "2000000", "2000000")},
            "turnover_spike",
        ),
    ],
)
def test_soft_trigger_sends_to_a_person(overrides: dict[str, Any], code: str) -> None:
    decision = decide(v3(**overrides))
    assert decision.outcome == "MANUAL_REVIEW"
    assert ReasonCode.ROUTE_SOFT_TRIGGER in decision.reason_codes
    assert [t.code for t in decision.triggers] == [code]
    assert hit(decision, f"trigger.{code}").matched


def test_head_from_registration_is_not_a_change() -> None:
    young = company(
        tax_arrears=Decimal(0), account_blocks=0, head_tenure_months=3, head_since_registration=True
    )
    decision = decide(v3(company=young))
    assert decision.triggers == ()
    assert hit(decision, "trigger.head_change").detail == (
        "руководитель по ЕГРЮЛ не менялся с регистрации"
    )


def test_even_turnover_is_not_a_spike() -> None:
    decision = decide(v3(cashflow=statement(*["1000000"] * 12)))
    assert decision.triggers == ()
    assert "×1.00, порог > ×1.5" in hit(decision, "trigger.turnover_spike").detail


def test_unknown_data_does_not_trigger() -> None:
    unknown = company(tax_arrears=None, account_blocks=0, head_tenure_months=None)
    decision = decide(v3(company=unknown))
    assert decision.triggers == ()
    assert "проверка не выполнена" in hit(decision, "trigger.head_change").detail
    assert "проверка не выполнена" in hit(decision, "trigger.turnover_spike").detail


# --- матрица грейд × сумма ---


def test_weak_grade_within_the_auto_band_is_approved_with_a_guarantee() -> None:
    decision = decide(v3(product=WIDE, score=score("F", "0.05")))
    assert decision.outcome == "APPROVE"
    assert decision.terms is not None
    assert "Поручительство собственника бизнеса" in decision.terms.conditions
    assert hit(decision, "offer.guarantee").matched


def test_weak_grade_above_the_auto_band_goes_to_a_person() -> None:
    decision = decide(
        v3(product=WIDE, score=score("F", "0.05"), request=RequestInput(Decimal("8000000"), 24))
    )
    assert decision.outcome == "MANUAL_REVIEW"
    assert decision.reason_codes == (ReasonCode.ROUTE_RISK_MATRIX,)


def test_grade_out_of_the_matrix_is_rejected() -> None:
    decision = decide(
        v3(product=WIDE, score=score("H", "0.12"), request=RequestInput(Decimal("5000000"), 24))
    )
    assert decision.outcome == "REJECT"
    assert decision.reason_codes == (ReasonCode.STOP_RISK_MATRIX,)
    assert decision.terms is None
    assert "ручная до 3 000 000 → отказ" in hit(decision, "strategy.risk_matrix").detail


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"sources_failed": ("kontur",)}, ReasonCode.ROUTE_SOURCES_FAILED),
        (
            {
                "company": company(
                    tax_arrears=Decimal("1000"), account_blocks=0, head_tenure_months=60
                )
            },
            ReasonCode.ROUTE_SOFT_TRIGGER,
        ),
    ],
)
def test_incomplete_data_and_triggers_go_before_the_matrix(
    overrides: dict[str, Any], reason: ReasonCode
) -> None:
    weak = v3(
        product=WIDE,
        score=score("H", "0.12"),
        request=RequestInput(Decimal("5000000"), 24),
        **overrides,
    )
    decision = decide(weak)
    assert decision.outcome == "MANUAL_REVIEW"
    assert reason in decision.reason_codes
    assert ReasonCode.ROUTE_RISK_MATRIX in decision.reason_codes


# --- лимит: минимум из ограничений ---


def test_turnover_limits_the_counter_offer() -> None:
    decision = decide(v3(cashflow=statement(*["300000"] * 12, net="500000")))
    assert decision.outcome == "COUNTER_OFFER"
    assert decision.limits.by_turnover == Decimal("1800000.00")
    assert decision.limits.binding == "by_turnover"
    assert decision.terms is not None and decision.terms.amount == Decimal("1800000.00")
    assert ReasonCode.LIMIT_BY_TURNOVER in decision.reason_codes
    assert "ограничена оборотами по счёту" in decision.client_explanation


def test_group_debt_limits_the_counter_offer() -> None:
    bureau = BureauInput(
        True, 0, Decimal("180000"), current_overdue_days=0, debt_balance=Decimal("99000000")
    )
    decision = decide(v3(bureau=bureau))
    assert decision.limits.by_group == Decimal("1000000.00")
    assert decision.limits.binding == "by_group"
    assert decision.terms is not None and decision.terms.amount == Decimal("1000000.00")
    assert ReasonCode.LIMIT_BY_GROUP in decision.reason_codes


def test_every_constraint_is_in_the_limits() -> None:
    limits = decide(v3()).limits
    assert limits.by_grade == Decimal("60000000.00")
    assert limits.by_group == Decimal("97000000.00")
    assert limits.by_turnover is None  # выписки нет — по оборотам не ограничиваем
    assert limits.final == limits.by_capacity and limits.binding == "by_capacity"


def test_no_bureau_no_group_limit() -> None:
    decision = decide(v3(bureau=BureauInput(False, None, Decimal(0)), sources_failed=("bki",)))
    assert decision.limits.by_group is None
    assert hit(decision, "limits.group").detail == "БКИ недоступно — долг группы неизвестен"


# --- ставка из компонент ---


def test_rate_is_funding_plus_expected_loss_plus_capital_plus_margin() -> None:
    gov = product(rate_base=Decimal("20"), rate_max=Decimal("30"))
    decision = decide(v3(product=gov, score=score("E", "0.0345")))
    parts = decision.rate_breakdown
    assert parts is not None
    assert parts.funding == Decimal("17.50")
    assert parts.expected_loss == Decimal("1.55")  # 0,0345 × 0,45 × 100
    assert parts.total == decision.rate == Decimal("24.55")


def test_secured_loan_has_lower_loss() -> None:
    inp = v3(
        product=secured(),
        collateral=CollateralInput("real_estate", Decimal("6000000")),
        score=score("E", "0.0345"),
    )
    parts = decide(inp).rate_breakdown
    assert parts is not None and parts.expected_loss == Decimal("0.86")  # LGD 0,25


def test_unknown_pd_is_priced_cautiously() -> None:
    decision = decide(v3(score=score("B", None)))
    assert decision.rate_breakdown is not None
    assert decision.rate_breakdown.expected_loss == Decimal("4.50")  # 0,10 × 0,45
    assert "PD неизвестна, берём 0.10" in hit(decision, "pricing.expected_loss").detail


# --- шкалы грейдов ---


def test_grades_move_between_scales() -> None:
    assert on_scale("A", from_pd_model=False, scale=PD_SCALE) == "B"
    assert on_scale("E", from_pd_model=False, scale=PD_SCALE) == "J"
    assert on_scale("F", from_pd_model=True, scale=LEGACY_SCALE) == "C"
    assert on_scale("J", from_pd_model=True, scale=LEGACY_SCALE) == "E"
    assert on_scale("C", from_pd_model=True, scale=PD_SCALE) == "C"
    assert on_scale("C", from_pd_model=False, scale=LEGACY_SCALE) == "C"


# --- предодобрение ---


def pre(grade: str, pd: str) -> PreApprovalInput:
    return PreApprovalInput(
        product=product(),
        grade=grade,  # type: ignore[arg-type]
        score=800,
        registry_status="active",
        annual_revenue=Decimal("48000000"),
        okved_main="56.10",
        in_msp_registry=True,
        pd_12m=Decimal(pd),
    )


def test_pre_approval_is_one_grade_more_cautious() -> None:
    offer = POLICY.pre_approve(pre("A", "0.0041"), key_rate=KEY_RATE)
    assert offer is not None
    assert offer.max_amount == Decimal("21600000.00")  # k(B) 0,45 × 48 млн
    assert offer.rate_from == Decimal("23.50")
    assert "PD 0.0041" in offer.factors_summary[0]


def test_pre_approval_stays_within_what_automation_approves() -> None:
    offer = POLICY.pre_approve(pre("C", "0.0153"), key_rate=KEY_RATE)
    # Грейд C → по D: k 0,3 × 48 млн = 14,4 млн, автоматика D–E — до 15 млн.
    assert offer is not None and offer.max_amount == Decimal("14400000.00")


@pytest.mark.parametrize(("grade", "pd"), [("H", "0.12"), ("I", "0.20"), ("J", "0.5")])
def test_weak_grades_get_no_pre_approval(grade: str, pd: str) -> None:
    assert POLICY.pre_approve(pre(grade, pd), key_rate=KEY_RATE) is None
