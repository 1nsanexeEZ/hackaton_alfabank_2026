"""Правила policy_v7: стоп-факторы до модели и «Данные полные?», как на общей схеме.

- `screen` — отдельный шаг процесса до скоринга: стоп-фактор → решение без модели, иначе None;
- в `decide` стоп-факторы идут раньше проверки, есть ли результат скоринга: без скоринга
  стоп-фактор всё равно даёт отказ (в policy_v6 — ручная проверка);
- скоринг пометил данные неполными (`quality = degraded`) → ручная проверка, спорная;
- две модели и матрица грейд × сумма вместе: решает строже из двух.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from typing import Any

import pytest

from src.modules.decision.domain.model import (
    BankStopListInput,
    DecisionInput,
    PolicyDecision,
    PreApprovalInput,
    ReasonCode,
    RequestInput,
)
from src.modules.decision.facade import review_kind
from src.modules.decision.infrastructure.config_loader import load_policy
from tests.decision.unit.test_credit_policy_rules import company
from tests.decision.unit.test_credit_policy_v3_rules import WIDE, hit
from tests.decision.unit.test_credit_policy_v5_rules import models
from tests.decision.unit.test_credit_policy_v6_rules import LISTED, v6

POLICY = load_policy("policy_v7")
V6 = load_policy("policy_v6")
KEY_RATE = POLICY.config.key_rate_reference
LIQUIDATED = company(registry_status="liquidated")


def v7(**overrides: Any) -> DecisionInput:
    return v6(**overrides)


def decide(inp: DecisionInput) -> PolicyDecision:
    return POLICY.decide(inp, key_rate=KEY_RATE)


def screen(inp: DecisionInput) -> PolicyDecision | None:
    return POLICY.screen(inp, key_rate=KEY_RATE)


def test_clean_application_passes_the_screen() -> None:
    assert screen(v7()) is None


def test_stop_factor_rejects_without_the_model() -> None:
    decision = screen(v7(company=LIQUIDATED))
    assert decision is not None
    assert decision.outcome == "REJECT" and decision.policy_version == "policy_v7"
    assert decision.reason_codes == (ReasonCode.STOP_LIQUIDATION,)
    assert hit(decision, "stop.registry_status").matched
    rules = {h.rule for h in decision.rule_trace}
    assert not rules & {"strategy.two_models", "input.scoring", "stop.grade"}
    assert decision.rate is None and decision.terms is None


def test_screen_ignores_the_score_and_its_hints() -> None:
    """Результат скоринга прошлой итерации (после дозапроса) к стоп-факторам не относится."""
    decision = screen(v7(company=LIQUIDATED))
    without_score = screen(v7(company=LIQUIDATED, score=None))
    assert decision == without_score


def test_aml_list_is_still_first() -> None:
    decision = screen(v7(aml=LISTED, company=LIQUIDATED))
    assert decision is not None and decision.reason_codes == (ReasonCode.STOP_AML_LISTED,)
    assert [h.rule for h in decision.rule_trace] == ["aml.lists", "aml.zsk_stop"]


def test_entrepreneur_without_consent_goes_to_a_person() -> None:
    """ст. 16 152-ФЗ: отказ ИП по стоп-фактору без согласия на авторешение готовит человек."""
    ie = company(registry_status="liquidated", legal_form="IE")
    decision = screen(v7(company=ie, automated_decision_consent=False))
    assert decision is not None and decision.outcome == "MANUAL_REVIEW"
    assert decision.reason_codes == (
        ReasonCode.ROUTE_AUTOMATED_DECISION_CONSENT,
        ReasonCode.STOP_LIQUIDATION,
    )
    agreed = screen(v7(company=ie, automated_decision_consent=True))
    assert agreed is not None and agreed.outcome == "REJECT"


def test_stop_factor_without_a_score_is_rejected() -> None:
    """policy_v6 отдавала такую заявку андеррайтеру, не проверив стоп-факторы."""
    inp = v7(company=LIQUIDATED, score=None)
    assert decide(inp).outcome == "REJECT"
    assert decide(inp).reason_codes == (ReasonCode.STOP_LIQUIDATION,)
    assert V6.decide(inp, key_rate=KEY_RATE).outcome == "MANUAL_REVIEW"


def test_no_score_without_a_stop_factor_is_for_a_person() -> None:
    decision = decide(v7(score=None))
    assert decision.outcome == "MANUAL_REVIEW"
    assert decision.reason_codes == (ReasonCode.ROUTE_SOURCES_FAILED,)
    assert hit(decision, "stop.registry_status").matched is False


def test_with_a_score_the_trace_is_that_of_v6_plus_quality_and_matrix() -> None:
    inp = v7(score=replace(models(), quality="ok"))
    v6_decision = V6.decide(inp, key_rate=KEY_RATE)
    v7_decision = decide(inp)
    assert v7_decision.outcome == v6_decision.outcome == "APPROVE"
    quality = hit(v7_decision, "route.data_quality")
    assert not quality.matched and quality.detail == "данные полные"
    assert not hit(v7_decision, "strategy.risk_matrix").matched
    added = {
        "route.data_quality",
        "strategy.risk_matrix",
        "stop.unreliable_data",
        "stop.mass_head",
        "stop.business_age",
        "stop.bank_stop_list",
    }
    assert tuple(h for h in v7_decision.rule_trace if h.rule not in added) == v6_decision.rule_trace


# --- «Данные полные?» ------------------------------------------------------------------------

DEGRADED = replace(
    models(),
    quality="degraded",
    quality_reasons=("source_failed:bki", "completeness_below:0.583"),
)


def test_degraded_data_is_for_a_person() -> None:
    decision = decide(v7(score=DEGRADED))
    assert decision.outcome == "MANUAL_REVIEW"
    assert decision.reason_codes == (ReasonCode.ROUTE_SOURCES_FAILED,)
    assert review_kind(decision.outcome, decision.reason_codes) == "dispute"
    detail = hit(decision, "route.data_quality").detail
    assert detail == (
        "данные неполные: не ответили источники: bki; данные есть по доле признаков 0.583 — "
        "ниже порога — решает человек"
    )
    # Ставка и лимиты посчитаны — андеррайтер видит их рядом с моделями.
    assert decision.rate is not None and decision.limits.by_revenue is not None


def test_both_models_red_on_degraded_data_are_not_a_reject() -> None:
    red = replace(models("red", "red"), quality="degraded", quality_reasons=("source_failed:fns",))
    decision = decide(v7(score=red))
    assert decision.outcome == "MANUAL_REVIEW"
    assert ReasonCode.STOP_MODELS_HIGH_RISK not in decision.reason_codes


# --- две модели и матрица грейд × сумма -------------------------------------------------------

GRADE_D = replace(models(), grade="D", pd_12m=Decimal("0.0250"), quality="ok")


def at(amount: str) -> RequestInput:
    return RequestInput(amount=Decimal(amount), term_months=36)


def test_both_models_green_but_above_the_band_is_for_a_person() -> None:
    """Грейд D: обе модели в зелёной зоне, но автоматика корзины D–E — до 15 млн."""
    decision = decide(v7(score=GRADE_D, request=at("20000000")))
    assert decision.outcome == "MANUAL_REVIEW"
    assert decision.reason_codes == (ReasonCode.ROUTE_RISK_MATRIX,)
    assert review_kind(decision.outcome, decision.reason_codes) == "check"
    matrix = hit(decision, "strategy.risk_matrix")
    assert matrix.matched and "корзина D–E" in matrix.detail
    assert not hit(decision, "strategy.two_models").matched
    # policy_v6 знала только зоны моделей и решила бы сама.
    assert V6.decide(v7(score=GRADE_D, request=at("20000000")), key_rate=KEY_RATE).outcome in (
        "APPROVE",
        "COUNTER_OFFER",
    )


def test_above_the_manual_band_is_a_reject() -> None:
    decision = decide(v7(score=GRADE_D, request=at("60000000")))
    assert decision.outcome == "REJECT"
    assert decision.reason_codes == (ReasonCode.STOP_RISK_MATRIX,)


def test_within_the_band_the_models_decide() -> None:
    decision = decide(v7(score=replace(GRADE_D, ml_grade="E"), request=at("10000000")))
    assert decision.outcome == "MANUAL_REVIEW"
    assert decision.reason_codes == (ReasonCode.ROUTE_MODELS_CHECK,)
    assert not hit(decision, "strategy.risk_matrix").matched


def test_pre_approval_is_capped_by_the_band() -> None:
    """Оценка C → осторожный грейд D: не выше автоматики корзины D–E (15 млн), хотя по выручке
    и потолку грейда вышло бы 30 млн."""
    inp = PreApprovalInput(
        product=replace(WIDE, amount_max=Decimal("100000000")),
        grade="C",
        score=720,
        registry_status="active",
        annual_revenue=Decimal("200000000"),
        okved_main="56.10",
        pd_12m=Decimal("0.0150"),
    )
    v7_offer = POLICY.pre_approve(inp, key_rate=KEY_RATE)
    v6_offer = V6.pre_approve(inp, key_rate=KEY_RATE)
    assert v7_offer is not None and v7_offer.max_amount == Decimal("15000000")
    assert v6_offer is not None and v6_offer.max_amount == Decimal("30000000")


# --- остальные стоп-факторы таблицы общей схемы ---------------------------------------------


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"company": company(registry_status="reorganizing")}, ReasonCode.STOP_REORGANIZATION),
        ({"company": company(registry_status="excluded")}, ReasonCode.STOP_EXCLUDED_FROM_REGISTRY),
        ({"company": company(unreliable=("address", "head"))}, ReasonCode.STOP_UNRELIABLE_DATA),
        ({"company": company(mass_head=True)}, ReasonCode.STOP_MASS_HEAD),
        (
            {
                "company": company(business_age_months=4),
                "product": replace(WIDE, min_business_age_months=12),
            },
            ReasonCode.STOP_BUSINESS_TOO_YOUNG,
        ),
        (
            {"bank_stop_list": BankStopListInput("ok", listed=True, reason="подлог")},
            ReasonCode.STOP_BANK_STOP_LIST,
        ),
    ],
)
def test_new_stop_factor_rejects_before_the_model(
    overrides: dict[str, Any], reason: ReasonCode
) -> None:
    decision = screen(v7(**overrides))
    assert decision is not None and decision.outcome == "REJECT"
    assert decision.reason_codes == (reason,)


def test_new_stop_factors_trace_when_clean() -> None:
    decision = decide(
        v7(
            company=company(mass_head=False, business_age_months=72),
            bank_stop_list=BankStopListInput("ok"),
        )
    )
    assert decision.outcome == "APPROVE"
    details = {
        rule: hit(decision, rule).detail
        for rule in (
            "stop.unreliable_data",
            "stop.mass_head",
            "stop.business_age",
            "stop.bank_stop_list",
        )
    }
    assert details == {
        "stop.unreliable_data": "отметок о недостоверности сведений в ЕГРЮЛ нет",
        "stop.mass_head": "руководитель не массовый",
        "stop.business_age": "срок работы 72 мес., минимум продукта 0 мес.",
        "stop.bank_stop_list": "во внутреннем стоп-листе банка компании нет",
    }


def test_stop_list_down_is_not_a_reject() -> None:
    """Источник не ответил — проверка не выполнена; на ручную отправляет сбой источников."""
    decision = decide(
        v7(bank_stop_list=BankStopListInput("failed"), sources_failed=("bank_stop_list",))
    )
    assert decision.outcome == "MANUAL_REVIEW"
    assert ReasonCode.ROUTE_SOURCES_FAILED in decision.reason_codes
    assert hit(decision, "stop.bank_stop_list").detail == (
        "стоп-лист банка не ответил — проверка не выполнена"
    )


def test_listed_reason_stays_with_the_bank() -> None:
    decision = screen(v7(bank_stop_list=BankStopListInput("ok", listed=True, reason="подлог")))
    assert decision is not None
    assert "подлог" in hit(decision, "stop.bank_stop_list").detail
    assert "подлог" not in decision.client_explanation


def test_result_before_quality_is_not_degraded() -> None:
    decision = decide(v7())
    assert decision.outcome == "APPROVE"
    assert hit(decision, "route.data_quality").detail == (
        "качество данных скоринг не оценивал — проверка не выполнена"
    )
