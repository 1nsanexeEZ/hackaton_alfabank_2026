"""Golden S-1…S-7 политики v7: входы как в v6. Эталоны — в `golden_v7/`.

Исходы и трасса решения — те же, что в v6. Разница — в процессе: «Закат» (S-4) ликвидируется, с
просрочками и недоимкой, поэтому отказ ему даёт уже шаг «Стоп-факторы», без скоринга; остальные
демо-компании этот шаг проходят.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from src.modules.decision.domain.model import PolicyDecision
from src.modules.decision.facade import review_kind
from src.modules.decision.infrastructure.config_loader import load_policy
from tests.decision.unit.decision_world import ALL_SOURCES, SCENARIOS, DecisionWorld, build_world
from tests.decision.unit.test_decision_golden_v6 import golden_json

_GOLDEN = Path(__file__).resolve().parent / "golden_v7"
_KEY_RATE = Decimal("16.50")
_POLICY = load_policy("policy_v7")


async def collect(name: str) -> tuple[DecisionWorld, object]:
    world = await build_world(name, sources=ALL_SOURCES, head_consent=True)
    collected = await world.builder(_POLICY).collect(world.application_id)
    return world, collected.decision_input


async def decide(name: str) -> tuple[DecisionWorld, PolicyDecision]:
    world, inp = await collect(name)
    return world, _POLICY.decide(inp, key_rate=_KEY_RATE)  # type: ignore[arg-type]


@pytest.mark.parametrize("name", sorted(SCENARIOS))
async def test_scenario_matches_golden(name: str) -> None:
    world, decision = await decide(name)
    expected = json.loads((_GOLDEN / f"{name}.json").read_text(encoding="utf-8"))
    assert golden_json(world, decision) == expected


@pytest.mark.parametrize("name", sorted(set(SCENARIOS) - {"s4_zakat"}))
async def test_demo_companies_pass_the_stop_factors(name: str) -> None:
    _, inp = await collect(name)
    assert _POLICY.screen(inp, key_rate=_KEY_RATE) is None  # type: ignore[arg-type]


async def test_s4_zakat_is_rejected_before_scoring() -> None:
    _, inp = await collect("s4_zakat")
    stopped = _POLICY.screen(inp, key_rate=_KEY_RATE)  # type: ignore[arg-type]
    assert stopped is not None and stopped.outcome == "REJECT"
    _, decided = await decide("s4_zakat")
    # Те же стоп-факторы, что в решении после скоринга; модели в трассе стопа нет.
    assert stopped.reason_codes == decided.reason_codes
    assert stopped.reason_codes[0] == "STOP_LIQUIDATION"
    assert not any(h.rule.startswith("strategy.") for h in stopped.rule_trace)


@pytest.mark.parametrize(
    ("name", "outcome", "review"),
    [
        ("s1_romashka", "APPROVE", None),
        ("s2_ivanov", "MANUAL_REVIEW", "check"),
        ("s3_vector", "MANUAL_REVIEW", "dispute"),
        ("s4_zakat", "REJECT", None),
        ("s5a_progress", "REQUEST_INFO", None),
        ("s5b_progress", "MANUAL_REVIEW", "dispute"),
        ("s6_sboy", "MANUAL_REVIEW", "dispute"),
        ("s7_romashka_mortgage", "MANUAL_REVIEW", "check"),
    ],
)
async def test_outcomes_of_the_demo_are_those_of_v6(
    name: str, outcome: str, review: str | None
) -> None:
    _, decision = await decide(name)
    assert decision.outcome == outcome and decision.policy_version == "policy_v7"
    assert review_kind(decision.outcome, decision.reason_codes) == review
