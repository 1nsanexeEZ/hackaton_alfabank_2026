"""Golden S-1…S-7 политики v5: те же входы, что в v3 и v4, скоринг — PD-модель и рядом
ML-модель, решение — по паре их зон. Эталоны — в `golden_v5/`.

Исходы демо, кроме S-2, те же, что в v3: Ромашка одобрена (обе модели в зелёной зоне), Закат
отклонён по стоп-факторам, остальные — у андеррайтера. S-2 (Иванов, грейд E у обеих моделей) —
теперь проверка андеррайтером, а не автоматическое встречное предложение. У ручной проверки
есть вид: проверка (check) или спорная (dispute).
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from src.modules.decision.domain.model import PolicyDecision, ReasonCode
from src.modules.decision.facade import review_kind
from src.modules.decision.infrastructure.config_loader import load_policy
from tests.decision.unit.decision_world import ALL_SOURCES, SCENARIOS, DecisionWorld, build_world
from tests.decision.unit.test_decision_golden import as_json

_GOLDEN = Path(__file__).resolve().parent / "golden_v5"
_KEY_RATE = Decimal("16.50")


async def decide(name: str) -> tuple[DecisionWorld, PolicyDecision]:
    world = await build_world(name, sources=ALL_SOURCES, head_consent=True)
    policy = load_policy("policy_v5")
    collected = await world.builder(policy).collect(world.application_id)
    return world, policy.decide(collected.decision_input, key_rate=_KEY_RATE)


def golden_json(world: DecisionWorld, decision: PolicyDecision) -> dict[str, object]:
    data = as_json(world, decision)
    ml = world.result.ml
    assert ml is not None
    data["scoring"]["ml"] = {"grade": ml.grade, "pd_12m": str(ml.pd_12m)}  # type: ignore[index]
    data["review"] = review_kind(decision.outcome, decision.reason_codes)
    return data


def _detail(decision: PolicyDecision, rule: str) -> str:
    return next(h.detail for h in decision.rule_trace if h.rule == rule)


@pytest.mark.parametrize("name", sorted(SCENARIOS))
async def test_scenario_matches_golden(name: str) -> None:
    world, decision = await decide(name)
    expected = json.loads((_GOLDEN / f"{name}.json").read_text(encoding="utf-8"))
    assert golden_json(world, decision) == expected


@pytest.mark.parametrize(
    ("name", "outcome", "review", "grade", "ml_grade"),
    [
        ("s1_romashka", "APPROVE", None, "A", "C"),
        ("s2_ivanov", "MANUAL_REVIEW", "check", "E", "E"),
        ("s3_vector", "MANUAL_REVIEW", "dispute", "F", "F"),
        ("s4_zakat", "REJECT", None, "J", "J"),
        ("s5a_progress", "REQUEST_INFO", None, "C", "F"),
        ("s5b_progress", "MANUAL_REVIEW", "dispute", "D", "F"),
        ("s6_sboy", "MANUAL_REVIEW", "dispute", "B", "C"),
        ("s7_romashka_mortgage", "MANUAL_REVIEW", "check", "C", "D"),
    ],
)
async def test_outcomes_of_the_demo(
    name: str, outcome: str, review: str | None, grade: str, ml_grade: str
) -> None:
    world, decision = await decide(name)
    assert decision.outcome == outcome and decision.policy_version == "policy_v5"
    assert review_kind(decision.outcome, decision.reason_codes) == review
    assert world.result.ml is not None
    assert (world.result.grade, world.result.ml.grade) == (grade, ml_grade)


async def test_s1_romashka_both_models_green() -> None:
    _, decision = await decide("s1_romashka")
    assert _detail(decision, "strategy.two_models") == (
        "PD-модель: грейд A (PD 0.41%) — зелёная; ML-модель: грейд C (PD 1.39%) — зелёная → "
        "одобрение, дальше лимиты"
    )


async def test_s2_ivanov_both_models_yellow_is_a_check() -> None:
    _, decision = await decide("s2_ivanov")
    assert decision.reason_codes == (ReasonCode.ROUTE_MODELS_CHECK,)
    assert decision.terms is None
    assert "жёлтая; ML-модель: грейд E" in _detail(decision, "strategy.two_models")


async def test_s4_zakat_stops_before_the_models() -> None:
    _, decision = await decide("s4_zakat")
    assert ReasonCode.STOP_MODELS_HIGH_RISK not in decision.reason_codes
    assert all(h.rule != "strategy.two_models" for h in decision.rule_trace)


@pytest.mark.parametrize("name", sorted(SCENARIOS))
async def test_client_texts_carry_no_internal_details(name: str) -> None:
    world, decision = await decide(name)
    for text in (decision.client_explanation, *decision.improvement_hints):
        assert text
        assert not any(code.value in text for code in ReasonCode)
        for internal in ("скор", "грейд", "PD", "ML", "модел", "LGD", "policy"):
            assert internal not in text, (internal, text)
