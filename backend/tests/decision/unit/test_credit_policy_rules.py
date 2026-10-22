"""Каждое правило CreditPolicy отдельно, на границах (LTV ровно 0.7, платёж ровно 40%).

Вход собирается прямо в доменных типах: базовая заявка — «Ромашка» на 3 млн / 24 мес., грейд A,
одобряется как просили; тест меняет ровно то, что проверяет.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from typing import Any

import pytest

from src.core.domain import Money
from src.decision.domain.model import (
    AlternativeInput,
    BureauInput,
    CashflowInput,
    CollateralInput,
    CompanyInput,
    DecisionInput,
    PolicyDecision,
    ProductInput,
    ReasonCode,
    RequestInput,
    RuleHit,
    ScoreInput,
    SupportProgramInput,
)
from src.decision.domain.policy import annuity_payment, max_principal
from src.decision.infrastructure.config_loader import default_policy
from src.products.domain.calculator import PaymentCalculator

POLICY = default_policy()
KEY_RATE = POLICY.config.key_rate_reference
RICH = CashflowInput(
    Decimal("10000000"), gap_detected=False, gap_month=None, revenue_confirmed=True
)
ALTERNATIVES = (
    AlternativeInput("OVERDRAFT", True, Decimal("100000")),
    AlternativeInput("CREDIT_LINE", True, Decimal("1000000")),
    AlternativeInput("SECURED", True, Decimal("500000")),
)


def product(**overrides: Any) -> ProductInput:
    base = ProductInput(
        code="UNSECURED",
        amount_min=Decimal("300000"),
        amount_max=Decimal("30000000"),
        term_min_months=12,
        term_max_months=60,
        rate_base=Decimal("23.5"),
        rate_max=Decimal("30"),
        repayment_options=("annuity", "differentiated"),
        collateral_required=False,
        auto_decision_limit=Decimal("5000000"),
    )
    return replace(base, **overrides)


def secured(**overrides: Any) -> ProductInput:
    base = product(
        code="SECURED",
        amount_min=Decimal("500000"),
        amount_max=Decimal("150000000"),
        term_max_months=120,
        rate_base=Decimal("21.5"),
        rate_max=Decimal("27"),
        collateral_required=True,
        auto_decision_limit=Decimal("10000000"),
    )
    return replace(base, **overrides)


def company(**overrides: Any) -> CompanyInput:
    base = CompanyInput(
        legal_form="LLC",
        okved_main="56.10",
        registry_status="active",
        verification_status="verified",
        declared_revenue=Decimal("48000000"),
        declared_expenses=Decimal("41000000"),
        reported_revenue=Decimal("47500000"),
        disqualified_head=False,
        in_msp_registry=True,
    )
    return replace(base, **overrides)


def score(grade: str = "A", *flags: str) -> ScoreInput:
    return ScoreInput(score=790, grade=grade, flags=frozenset(flags))  # type: ignore[arg-type]


def make(**overrides: Any) -> DecisionInput:
    base = DecisionInput(
        product=product(),
        request=RequestInput(Decimal("3000000"), 24),
        company=company(),
        score=score(),
        bureau=BureauInput(True, 0, Decimal("180000")),
        cashflow=None,
        collateral=None,
        sources_failed=(),
        revenue_info_requested=False,
        alternatives=ALTERNATIVES,
    )
    return replace(base, **overrides)


def decide(inp: DecisionInput, key_rate: Decimal = KEY_RATE) -> PolicyDecision:
    return POLICY.decide(inp, key_rate=key_rate)


def hit(decision: PolicyDecision, rule: str) -> RuleHit:
    return next(h for h in decision.rule_trace if h.rule == rule)


def test_baseline_is_approved_and_traced_in_rule_order() -> None:
    decision = decide(make())
    assert decision.outcome == "APPROVE"
    groups = [h.rule.split(".", 1)[0] for h in decision.rule_trace]
    order = list(dict.fromkeys(groups))
    assert order == ["stop", "info", "pricing", "limits", "route", "cash_gap", "outcome"]


def test_decision_is_deterministic() -> None:
    assert decide(make()) == decide(make())


# --- 1. стоп-факторы ---


@pytest.mark.parametrize(
    ("status", "reason"),
    [
        ("liquidating", ReasonCode.STOP_LIQUIDATION),
        ("liquidated", ReasonCode.STOP_LIQUIDATION),
        ("bankrupt", ReasonCode.STOP_BANKRUPTCY),
    ],
)
def test_registry_status_stops(status: str, reason: ReasonCode) -> None:
    decision = decide(make(company=company(registry_status=status)))
    assert decision.outcome == "REJECT"
    assert decision.reason_codes == (reason,)
    assert decision.terms is None and decision.alternative_product_code is None


def test_disqualified_head_stops() -> None:
    decision = decide(make(company=company(disqualified_head=True)))
    assert decision.reason_codes == (ReasonCode.STOP_DISQUALIFIED_HEAD,)


def test_unknown_disqualification_does_not_stop() -> None:
    decision = decide(make(company=company(disqualified_head=None)))
    assert decision.outcome == "APPROVE"
    assert "не выполнена" in hit(decision, "stop.disqualified_head").detail


@pytest.mark.parametrize(("days", "stopped"), [(90, False), (91, True)])
def test_overdue_boundary_is_strictly_over_90_days(days: int, stopped: bool) -> None:
    decision = decide(make(bureau=BureauInput(True, days, Decimal("180000"))))
    assert (decision.outcome == "REJECT") is stopped
    assert (ReasonCode.STOP_OVERDUE_90 in decision.reason_codes) is stopped


def test_grade_e_stops() -> None:
    decision = decide(make(score=score("E")))
    assert decision.reason_codes == (ReasonCode.STOP_GRADE_E,)


def test_every_stop_factor_is_recorded() -> None:
    decision = decide(
        make(
            company=company(registry_status="liquidating", disqualified_head=True),
            bureau=BureauInput(True, 120, Decimal("300000")),
            score=score("E"),
        )
    )
    assert decision.reason_codes == (
        ReasonCode.STOP_LIQUIDATION,
        ReasonCode.STOP_DISQUALIFIED_HEAD,
        ReasonCode.STOP_OVERDUE_90,
        ReasonCode.STOP_GRADE_E,
    )
    assert all(hit(decision, rule).matched for rule in ("stop.registry_status", "stop.grade"))


# --- 2. дозапрос ---


def test_revenue_mismatch_requests_statement_once() -> None:
    decision = decide(make(score=score("B", "revenue_mismatch")))
    assert decision.outcome == "REQUEST_INFO"
    assert decision.requested_info is not None
    assert decision.requested_info.documents == ("bank_statement",)
    assert decision.requested_info.comment.startswith(
        "Подтвердите выручку выпиской по счёту за 6 месяцев"
    )
    assert not any(h.rule.startswith("pricing") for h in decision.rule_trace)


def test_revenue_mismatch_after_statement_goes_to_underwriter() -> None:
    decision = decide(make(score=score("B", "revenue_mismatch"), revenue_info_requested=True))
    assert decision.outcome == "MANUAL_REVIEW"
    assert decision.reason_codes == (ReasonCode.ROUTE_REVENUE_MISMATCH,)


# --- 3. ставка ---


@pytest.mark.parametrize(
    ("grade", "rate"),
    [("A", "23.50"), ("B", "25.00"), ("C", "27.00"), ("D", "29.50")],
)
def test_grade_premium(grade: str, rate: str) -> None:
    assert decide(make(score=score(grade), cashflow=RICH)).rate == Decimal(rate)


@pytest.mark.parametrize(("value", "rate"), [("3000000", "25.50"), ("2999999", "27.00")])
def test_collateral_discount_from_full_coverage(value: str, rate: str) -> None:
    inp = make(score=score("C"), collateral=CollateralInput("equipment", Decimal(value)))
    assert decide(inp).rate == Decimal(rate)


@pytest.mark.parametrize(
    ("key_rate", "rate"),
    [
        ("16.50", "27.00"),  # опорная: как в каталоге
        ("18.50", "29.00"),  # +2 п.п. ключевой → +2 п.п. внутри коридора
        ("25.00", "30.00"),  # упор в максимум продукта
        ("10.00", "23.50"),  # не ниже базовой ставки продукта
    ],
)
def test_key_rate_moves_rate_within_product(key_rate: str, rate: str) -> None:
    decision = decide(make(score=score("C"), cashflow=RICH), key_rate=Decimal(key_rate))
    assert decision.rate == Decimal(rate)
    assert decision.key_rate == Decimal(key_rate)
    assert hit(decision, "pricing.key_rate").matched is (Decimal(key_rate) != KEY_RATE)


def _gov_support() -> ProductInput:
    return product(
        code="GOV_SUPPORT",
        amount_min=Decimal("1000000"),
        amount_max=Decimal("100000000"),
        rate_base=Decimal("12"),
        rate_max=Decimal("18"),
        auto_decision_limit=Decimal("10000000"),
        support_program=SupportProgramInput(
            "MSP_PRIORITY", Decimal("15"), True, frozenset({"56", "62"})
        ),
    )


@pytest.mark.parametrize(
    ("overrides", "rate"),
    [
        ({}, "15.00"),  # проходит программу: 15,5 → потолок 15
        ({"in_msp_registry": False}, "15.50"),  # не в реестре МСП
        ({"okved_main": "47.19"}, "15.50"),  # отрасль не приоритетная
    ],
)
def test_gov_support_rate_cap(overrides: dict[str, Any], rate: str) -> None:
    inp = make(
        product=_gov_support(), company=company(**overrides), score=score("C"), cashflow=RICH
    )
    assert decide(inp).rate == Decimal(rate)


# --- 4. лимиты ---


@pytest.mark.parametrize(("grade", "k"), [("A", "0.5"), ("B", "0.4"), ("C", "0.25"), ("D", "0.15")])
def test_revenue_limit_uses_smaller_of_declared_and_fns(grade: str, k: str) -> None:
    decision = decide(make(score=score(grade)))
    assert decision.limits.by_revenue == Decimal(k) * Decimal("47500000")


def test_ltv_exactly_seventy_percent_is_approved() -> None:
    inp = make(
        product=secured(),
        request=RequestInput(Decimal("7000000"), 24),
        collateral=CollateralInput("real_estate", Decimal("10000000")),
        cashflow=RICH,
    )
    decision = decide(inp)
    assert decision.limits.by_ltv == Decimal("7000000.00")
    assert decision.outcome == "APPROVE"


def test_over_ltv_is_cut_to_collateral_limit() -> None:
    inp = make(
        product=secured(),
        request=RequestInput(Decimal("7010000"), 24),
        collateral=CollateralInput("real_estate", Decimal("10000000")),
        cashflow=RICH,
    )
    decision = decide(inp)
    assert decision.outcome == "COUNTER_OFFER"
    assert decision.terms is not None and decision.terms.amount == Decimal("7000000")
    assert decision.reason_codes == (ReasonCode.LIMIT_BY_LTV,)
    assert "стоимостью залога" in decision.client_explanation


def _cashflow_for_payment(payment: Decimal) -> CashflowInput:
    """Средний поток, при котором 40% свободного потока (без долгов) — ровно `payment`."""
    return CashflowInput(payment * Decimal("2.5"), False, None, True)


def test_payment_exactly_forty_percent_is_approved() -> None:
    payment = annuity_payment(Decimal("3000000"), 24, Decimal("23.50"))
    inp = make(bureau=BureauInput(True, 0, Decimal(0)), cashflow=_cashflow_for_payment(payment))
    decision = decide(inp)
    assert decision.outcome == "APPROVE"
    assert (
        f"{payment:,.2f}".replace(",", " ").replace(".", ",")
        in hit(decision, "outcome.approve").detail
    )


def test_payment_a_kopeck_over_forty_percent_is_countered() -> None:
    payment = annuity_payment(Decimal("3000000"), 24, Decimal("23.50"))
    cashflow = _cashflow_for_payment(payment - Decimal("0.01"))
    decision = decide(make(bureau=BureauInput(True, 0, Decimal(0)), cashflow=cashflow))
    assert decision.outcome == "COUNTER_OFFER"
    assert ReasonCode.LIMIT_BY_PAYMENT_CAPACITY in decision.reason_codes
    # Сумму сохранили, срок подобрали так, чтобы платёж прошёл.
    assert decision.terms is not None
    assert decision.terms.amount == Decimal("3000000")
    assert 24 < decision.terms.term_months <= 60
    assert ReasonCode.TERM_ADJUSTED in decision.reason_codes


def test_capacity_limit_is_inverse_annuity_of_forty_percent() -> None:
    decision = decide(make())
    # (48 млн − 41 млн) / 12 − 180 000 = 403 333,33 → платёж ≤ 161 333,33
    expected = max_principal(Decimal("161333.33"), 24, Decimal("23.50"))
    assert decision.limits.by_capacity == expected


def test_missing_expenses_assume_eighty_percent_of_revenue() -> None:
    decision = decide(make(company=company(declared_expenses=None)))
    assumption = hit(decision, "limits.expenses_assumption")
    assert assumption.matched and "0.8" in assumption.detail
    # 48 млн × 0,2 / 12 − 180 000 = 620 000 → платёж ≤ 248 000
    assert "248 000" in hit(decision, "limits.payment_capacity").detail


def test_statement_cash_flow_takes_priority_over_report() -> None:
    cashflow = CashflowInput(Decimal("500000"), False, None, True)
    decision = decide(make(company=company(declared_expenses=None), cashflow=cashflow))
    assert hit(decision, "limits.free_cash_flow").detail.startswith("по выписке")
    assert not any(h.rule == "limits.expenses_assumption" for h in decision.rule_trace)
    # (500 000 − 180 000) × 0,4 = 128 000
    assert "128 000" in hit(decision, "limits.payment_capacity").detail


def test_product_maximum_caps_the_offer() -> None:
    inp = make(
        product=product(auto_decision_limit=Decimal("100000000")),
        request=RequestInput(Decimal("35000000"), 60),
        company=company(declared_revenue=Decimal("100000000"), reported_revenue=None),
        cashflow=RICH,
    )
    decision = decide(inp)
    assert decision.outcome == "COUNTER_OFFER"
    assert decision.terms is not None and decision.terms.amount == Decimal("30000000")
    assert decision.reason_codes == (ReasonCode.LIMIT_BY_PRODUCT,)


def test_counter_offer_is_rounded_down_to_ten_thousand() -> None:
    inp = make(
        product=product(auto_decision_limit=Decimal("100000000")),
        request=RequestInput(Decimal("6000000"), 24),
        company=company(declared_revenue=Decimal("12345678"), reported_revenue=None),
        score=score("B"),
        cashflow=RICH,
    )
    decision = decide(inp)
    assert decision.limits.by_revenue == Decimal("4938271.20")
    assert decision.terms is not None
    assert decision.terms.amount == Decimal("4930000")
    assert decision.terms.term_months == 24
    assert decision.reason_codes == (ReasonCode.LIMIT_BY_REVENUE,)
    assert "выручкой" in decision.client_explanation


# --- 5. маршрутизация ---


@pytest.mark.parametrize(("amount", "routed"), [("5000000", False), ("5000001", True)])
def test_auto_decision_limit_boundary(amount: str, routed: bool) -> None:
    decision = decide(make(request=RequestInput(Decimal(amount), 24), cashflow=RICH))
    assert (decision.outcome == "MANUAL_REVIEW") is routed
    assert (ReasonCode.ROUTE_AMOUNT_OVER_AUTO_LIMIT in decision.reason_codes) is routed


def test_mortgage_with_zero_limit_is_always_manual() -> None:
    mortgage = secured(code="MORTGAGE", auto_decision_limit=Decimal(0))
    inp = make(
        product=mortgage,
        request=RequestInput(Decimal("3000000"), 120),
        collateral=CollateralInput("real_estate", Decimal("50000000")),
        cashflow=RICH,
    )
    decision = decide(inp)
    assert decision.outcome == "MANUAL_REVIEW"
    assert decision.reason_codes == (ReasonCode.ROUTE_AMOUNT_OVER_AUTO_LIMIT,)


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"score": score("D")}, ReasonCode.ROUTE_GRADE_D),
        ({"score": score("A", "verification_mismatch")}, ReasonCode.ROUTE_VERIFICATION_MISMATCH),
        (
            {"company": company(verification_status="mismatch")},
            ReasonCode.ROUTE_VERIFICATION_MISMATCH,
        ),
        ({"score": score("A", "bureau_unavailable")}, ReasonCode.ROUTE_SOURCES_FAILED),
        ({"sources_failed": ("egrul",)}, ReasonCode.ROUTE_SOURCES_FAILED),
        ({"score": score("A", "mass_address")}, ReasonCode.ROUTE_MASS_ADDRESS),
        ({"company": company(mass_address=True)}, ReasonCode.ROUTE_MASS_ADDRESS),
    ],
)
def test_routing_rules(overrides: dict[str, Any], reason: ReasonCode) -> None:
    decision = decide(make(**overrides))
    assert decision.outcome == "MANUAL_REVIEW"
    assert decision.reason_codes == (reason,)
    assert decision.terms is None
    # Лимиты и ставка посчитаны — андеррайтер видит их в решении.
    assert decision.limits.final is not None and decision.rate is not None


def test_thin_file_does_not_route() -> None:
    decision = decide(make(score=score("A", "thin_file")))
    assert decision.outcome == "APPROVE"
    assert hit(decision, "route.thin_file").matched is False


def test_routes_accumulate() -> None:
    decision = decide(
        make(
            request=RequestInput(Decimal("6000000"), 24),
            score=score("D", "verification_mismatch", "mass_address"),
        )
    )
    assert decision.reason_codes == (
        ReasonCode.ROUTE_AMOUNT_OVER_AUTO_LIMIT,
        ReasonCode.ROUTE_GRADE_D,
        ReasonCode.ROUTE_VERIFICATION_MISMATCH,
        ReasonCode.ROUTE_MASS_ADDRESS,
    )


def test_missing_scoring_result_goes_to_underwriter() -> None:
    decision = decide(make(score=None))
    assert decision.outcome == "MANUAL_REVIEW"
    assert decision.reason_codes == (ReasonCode.ROUTE_SOURCES_FAILED,)


# --- 6. исход и альтернативы ---


def _weak(**overrides: Any) -> DecisionInput:
    """Поток так мал, что даже на 60 мес. сумма ниже минимума продукта (300 000)."""
    values: dict[str, Any] = {
        "bureau": BureauInput(True, 0, Decimal(0)),
        "cashflow": CashflowInput(Decimal("10000"), False, None, True),
        **overrides,
    }
    return make(**values)


def test_limit_below_product_minimum_rejects_with_small_amount_product() -> None:
    decision = decide(_weak())
    assert decision.outcome == "REJECT"
    assert decision.reason_codes[0] == ReasonCode.LIMIT_BELOW_PRODUCT_MIN
    assert decision.alternative_product_code == "OVERDRAFT"
    assert "Можем предложить другой продукт: овердрафт." in decision.client_explanation


def test_reject_with_collateral_offers_secured_loan() -> None:
    decision = decide(_weak(collateral=CollateralInput("vehicle", Decimal("2000000"))))
    assert decision.outcome == "REJECT"
    assert decision.alternative_product_code == "SECURED"


def test_reject_without_suitable_alternative() -> None:
    cashflow = CashflowInput(Decimal("2000"), False, None, True)
    decision = decide(_weak(cashflow=cashflow))
    assert decision.outcome == "REJECT"
    assert decision.alternative_product_code is None


def test_counter_offer_term_stays_within_product() -> None:
    cashflow = CashflowInput(Decimal("150000"), False, None, True)
    decision = decide(make(bureau=BureauInput(True, 0, Decimal(0)), cashflow=cashflow))
    assert decision.outcome == "COUNTER_OFFER"
    assert decision.terms is not None
    assert 12 <= decision.terms.term_months <= 60
    assert decision.terms.amount % 10000 == 0


# --- кассовый разрыв ---

_GAP = CashflowInput(Decimal("10000000"), True, "2026-11", True)


def test_cash_gap_suggests_overdraft_in_offer() -> None:
    decision = decide(make(cashflow=_GAP))
    assert decision.outcome == "APPROVE"
    assert decision.alternative_product_code == "OVERDRAFT"
    assert ReasonCode.CASH_GAP_FORECAST in decision.reason_codes
    assert "разрыв в ноябре 2026, для него удобнее овердрафт" in decision.client_explanation
    assert decision.terms is not None
    assert any("ноябре 2026" in condition for condition in decision.terms.conditions)


def test_cash_gap_from_scoring_flag_only() -> None:
    decision = decide(make(score=score("A", "cash_gap")))
    assert decision.alternative_product_code == "OVERDRAFT"
    assert "ближайшие месяцы" in decision.client_explanation


def test_cash_gap_falls_back_to_credit_line() -> None:
    alternatives = (
        AlternativeInput("OVERDRAFT", False, Decimal("100000")),
        AlternativeInput("CREDIT_LINE", True, Decimal("1000000")),
    )
    decision = decide(make(cashflow=_GAP, alternatives=alternatives))
    assert decision.alternative_product_code == "CREDIT_LINE"
    assert "удобнее кредитная линия" in decision.client_explanation


def test_cash_gap_without_eligible_product() -> None:
    alternatives = (AlternativeInput("OVERDRAFT", False, Decimal("100000")),)
    decision = decide(make(cashflow=_GAP, alternatives=alternatives))
    assert decision.alternative_product_code is None
    assert "заложите резерв" in decision.client_explanation
    assert decision.terms is not None and decision.terms.conditions == ()


def test_cash_gap_never_suggests_the_requested_product() -> None:
    overdraft = product(
        code="OVERDRAFT",
        amount_min=Decimal("100000"),
        amount_max=Decimal("10000000"),
        term_min_months=3,
        term_max_months=12,
        rate_base=Decimal("24"),
        repayment_options=("interest_only",),
        auto_decision_limit=Decimal("10000000"),
    )
    inp = make(product=overdraft, request=RequestInput(Decimal("1000000"), 12), cashflow=_GAP)
    decision = decide(inp)
    assert decision.alternative_product_code == "CREDIT_LINE"
    assert decision.terms is not None and decision.terms.schedule_type == "interest_only"


def test_cash_gap_in_manual_review_stays_in_trace_only() -> None:
    decision = decide(make(cashflow=_GAP, score=score("D")))
    assert decision.outcome == "MANUAL_REVIEW"
    assert decision.alternative_product_code is None
    assert hit(decision, "cash_gap.forecast").matched


def test_offer_conditions_list_collateral_and_guarantee() -> None:
    inp = make(
        product=secured(guarantee="owner", target_use_confirmation=True),
        request=RequestInput(Decimal("3000000"), 24),
        collateral=CollateralInput("real_estate", Decimal("10000000")),
        cashflow=RICH,
    )
    decision = decide(inp)
    assert decision.terms is not None
    assert decision.terms.conditions == (
        "Залог: недвижимость",
        "Поручительство собственника бизнеса",
        "Подтверждение целевого использования средств",
    )


@pytest.mark.parametrize(
    ("amount", "term", "rate"),
    [("3000000", 24, "23.50"), ("1300000", 60, "27.00"), ("30000000", 120, "23.00")],
)
def test_payment_formula_matches_products(amount: str, term: int, rate: str) -> None:
    """Лимит считается той же формулой аннуитета, что и платёж в оффере (products)."""
    expected = PaymentCalculator().annuity(Money(Decimal(amount)), term, Decimal(rate))
    assert annuity_payment(Decimal(amount), term, Decimal(rate)) == expected.amount
