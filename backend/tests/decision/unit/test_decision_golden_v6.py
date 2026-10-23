"""Golden S-1…S-7 политики v6: входы как в v5 и проверка по 115-ФЗ на каждой заявке.
Эталоны — в `golden_v6/`.

Демо-компании и их люди чистые по перечням и ПДЛ, уровень риска ЗСК низкий, поэтому исходы — те
же, что в v5; в трассе первым правилом — проверка по 115-ФЗ с бенефициарами. ИП Иванов (S-2) —
на ручной проверке, а не с отказом или встречным предложением: правило ст. 16 152-ФЗ не нужно.
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
from tests.decision.unit.test_decision_golden import as_json

_GOLDEN = Path(__file__).resolve().parent / "golden_v6"
_KEY_RATE = Decimal("16.50")


async def decide(name: str) -> tuple[DecisionWorld, PolicyDecision]:
    world = await build_world(name, sources=ALL_SOURCES, head_consent=True)
    policy = load_policy("policy_v6")
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
async def test_outcomes_of_the_demo_are_those_of_v5(
    name: str, outcome: str, review: str | None
) -> None:
    _, decision = await decide(name)
    assert decision.outcome == outcome and decision.policy_version == "policy_v6"
    assert review_kind(decision.outcome, decision.reason_codes) == review
    lists = next(h for h in decision.rule_trace if h.rule == "aml.lists")
    assert not lists.matched and lists.detail.startswith("совпадений с перечнями нет")


async def test_s1_romashka_beneficial_owner_in_the_trace() -> None:
    _, decision = await decide("s1_romashka")
    assert _detail(decision, "aml.lists") == (
        "совпадений с перечнями нет (перечни на 2026-10-21); бенефициары: "
        "Смирнова Анна Сергеевна — 100.00%"
    )


async def test_s2_ivanov_entrepreneur_is_their_own_owner() -> None:
    _, decision = await decide("s2_ivanov")
    assert _detail(decision, "aml.lists").endswith("Иванов Иван Иванович (ИП)")
