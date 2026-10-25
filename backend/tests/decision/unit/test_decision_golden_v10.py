"""Golden S-1…S-7 политики v10: входы как в v9, клиент ответил, что действует к своей выгоде
(вопрос формы заявки). Эталоны — в `golden_v10/`.

Исходы — те же, что в v9: ответ есть, правило «нет ответа — к человеку» (`require_answers`) не
срабатывает. В трассе — что клиент действует к своей выгоде. Без ответа заявка уходит человеку.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from src.modules.decision.domain.model import PolicyDecision, ReasonCode
from src.modules.decision.facade import review_kind
from src.modules.decision.infrastructure.config_loader import load_policy
from tests.decision.unit.decision_world import SCENARIOS, V7_SOURCES, DecisionWorld, build_world
from tests.decision.unit.test_decision_golden_v6 import golden_json

_GOLDEN = Path(__file__).resolve().parent / "golden_v10"
_KEY_RATE = Decimal("16.50")
_POLICY = load_policy("policy_v10")


async def decide(name: str) -> tuple[DecisionWorld, PolicyDecision]:
    world = await build_world(name, sources=V7_SOURCES, head_consent=True, acts_for_itself=True)
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
async def test_outcomes_of_the_demo_are_those_of_v9(
    name: str, outcome: str, review: str | None
) -> None:
    _, decision = await decide(name)
    assert decision.outcome == outcome and decision.policy_version == "policy_v10"
    assert review_kind(decision.outcome, decision.reason_codes) == review


async def test_s1_romashka_answer_in_the_trace() -> None:
    _, decision = await decide("s1_romashka")
    rules = {h.rule: h for h in decision.rule_trace}
    assert rules["route.beneficiary"].detail == "клиент действует к своей выгоде"
    unknown = rules["route.third_parties_unknown"]
    assert not unknown.matched and unknown.detail == "сведения о третьих лицах есть"


async def test_without_the_answer_a_person_decides() -> None:
    """Заявка не из кабинета (API без ответа о третьем лице) — решает человек, спорная."""
    world = await build_world("s1_romashka", sources=V7_SOURCES, head_consent=True)
    collected = await world.builder(_POLICY).collect(world.application_id)
    decision = _POLICY.decide(collected.decision_input, key_rate=_KEY_RATE)
    assert decision.outcome == "MANUAL_REVIEW"
    assert decision.reason_codes == (ReasonCode.ROUTE_THIRD_PARTIES_UNKNOWN,)
    assert review_kind(decision.outcome, decision.reason_codes) == "dispute"
    assert {h.rule: h for h in decision.rule_trace}["route.third_parties_unknown"].detail == (
        "ответа о выгодоприобретателе нет"
    )
