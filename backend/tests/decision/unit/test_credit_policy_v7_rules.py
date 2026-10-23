"""Правила policy_v7: стоп-факторы до модели, как на общей схеме.

- `screen` — отдельный шаг процесса до скоринга: стоп-фактор → решение без модели, иначе None;
- в `decide` стоп-факторы идут раньше проверки, есть ли результат скоринга: без скоринга
  стоп-фактор всё равно даёт отказ (в policy_v6 — ручная проверка).
"""

from __future__ import annotations

from typing import Any

from src.modules.decision.domain.model import DecisionInput, PolicyDecision, ReasonCode
from src.modules.decision.infrastructure.config_loader import load_policy
from tests.decision.unit.test_credit_policy_rules import company
from tests.decision.unit.test_credit_policy_v3_rules import hit
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


def test_with_a_score_the_trace_is_that_of_v6() -> None:
    inp = v7()
    v6_decision = V6.decide(inp, key_rate=KEY_RATE)
    v7_decision = decide(inp)
    assert v7_decision.outcome == v6_decision.outcome == "APPROVE"
    assert v7_decision.rule_trace == v6_decision.rule_trace
