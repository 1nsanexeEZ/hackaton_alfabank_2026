"""Golden S-1…S-7 политики v9: входы как в v8. Эталоны — в `golden_v9/`.

Исходы — те же, что в v8: у демо-компаний нет иностранных участников, их виды деятельности не
лицензируются и не относятся к повышенному риску, бенефициаров клиент не называл. Группа риска по
115-ФЗ у всех низкая; в трассе — новые правила `aml.license` и `aml.risk_group`.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from src.modules.decision.domain.model import PolicyDecision
from src.modules.decision.facade import review_kind
from src.modules.decision.infrastructure.config_loader import load_policy
from tests.decision.unit.decision_world import SCENARIOS, V7_SOURCES, DecisionWorld, build_world
from tests.decision.unit.test_decision_golden_v6 import golden_json

_GOLDEN = Path(__file__).resolve().parent / "golden_v9"
_KEY_RATE = Decimal("16.50")
_POLICY = load_policy("policy_v9")


async def decide(name: str) -> tuple[DecisionWorld, PolicyDecision]:
    world = await build_world(name, sources=V7_SOURCES, head_consent=True)
    collected = await world.builder(_POLICY).collect(world.application_id)
    return world, _POLICY.decide(collected.decision_input, key_rate=_KEY_RATE)


@pytest.mark.parametrize("name", sorted(SCENARIOS))
async def test_scenario_matches_golden(name: str) -> None:
    world, decision = await decide(name)
    expected = json.loads((_GOLDEN / f"{name}.json").read_text(encoding="utf-8"))
    assert golden_json(world, decision) == expected


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
async def test_outcomes_of_the_demo_are_those_of_v8(
    name: str, outcome: str, review: str | None
) -> None:
    _, decision = await decide(name)
    assert decision.outcome == outcome and decision.policy_version == "policy_v9"
    assert review_kind(decision.outcome, decision.reason_codes) == review


async def test_s1_romashka_risk_group_in_the_trace() -> None:
    _, decision = await decide("s1_romashka")
    rules = {h.rule: h for h in decision.rule_trace}
    group = rules["aml.risk_group"]
    assert not group.matched
    assert group.detail == (
        "группа риска по 115-ФЗ: низкая — факторов риска нет; бенефициаров клиент не называл"
    )
    assert not rules["aml.license"].matched
    assert rules["aml.license"].detail == "ОКВЭД 56.10: лицензия не нужна"
    assert "route.aml_high_risk" not in rules
