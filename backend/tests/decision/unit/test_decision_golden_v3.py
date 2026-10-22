"""Golden S-1…S-7 политики v3: обогащение со всеми источниками, как в v2, скоринг — PD-модель
(грейды A–J, PD), решение — стратегия общей схемы. Эталоны — в `golden_v3/`.

Исходы демо те же, что в v1 и v2; меняются ставка (из компонент), лимиты (минимум из всех
ограничений с `binding`) и трасса: матрица грейд × сумма, мягкие триггеры.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from src.modules.decision.domain.model import PolicyDecision, ReasonCode
from src.modules.decision.infrastructure.config_loader import default_policy
from tests.decision.unit.decision_world import ALL_SOURCES, SCENARIOS, DecisionWorld, build_world
from tests.decision.unit.test_decision_golden import as_json

_GOLDEN = Path(__file__).resolve().parent / "golden_v3"
_KEY_RATE = Decimal("16.50")


async def decide(name: str, *, head_consent: bool = True) -> tuple[DecisionWorld, PolicyDecision]:
    world = await build_world(name, sources=ALL_SOURCES, head_consent=head_consent)
    policy = default_policy()
    collected = await world.builder(policy).collect(world.application_id)
    return world, policy.decide(collected.decision_input, key_rate=_KEY_RATE)


def _trace(decision: PolicyDecision) -> dict[str, tuple[bool, str]]:
    return {hit.rule: (hit.matched, hit.detail) for hit in decision.rule_trace}


def test_v3_is_the_default_policy() -> None:
    assert default_policy().version == "policy_v3"


@pytest.mark.parametrize("name", sorted(SCENARIOS))
async def test_scenario_matches_golden(name: str) -> None:
    world, decision = await decide(name)
    expected = json.loads((_GOLDEN / f"{name}.json").read_text(encoding="utf-8"))
    assert as_json(world, decision) == expected


@pytest.mark.parametrize(
    ("name", "outcome", "grade"),
    [
        ("s1_romashka", "APPROVE", "A"),
        ("s2_ivanov", "COUNTER_OFFER", "E"),
        ("s3_vector", "MANUAL_REVIEW", "F"),
        ("s4_zakat", "REJECT", "J"),
        ("s5a_progress", "REQUEST_INFO", "C"),
        ("s5b_progress", "MANUAL_REVIEW", "D"),
        ("s6_sboy", "MANUAL_REVIEW", "B"),
        ("s7_romashka_mortgage", "MANUAL_REVIEW", "C"),
    ],
)
async def test_outcomes_of_the_demo_stay(name: str, outcome: str, grade: str) -> None:
    world, decision = await decide(name)
    assert decision.outcome == outcome
    assert decision.policy_version == "policy_v3"
    assert world.result.grade == grade and world.result.pd_12m is not None


async def test_s1_romashka_rate_from_components_and_binding_limit() -> None:
    _, decision = await decide("s1_romashka")
    assert decision.rate_breakdown is not None
    parts = decision.rate_breakdown
    assert (parts.funding, parts.capital, parts.margin) == (
        Decimal("17.50"),
        Decimal("2.0"),
        Decimal("3.5"),
    )
    # 17,5 + EL + 2 + 3,5 ниже базы продукта — ставка в коридоре 23,5–30.
    assert parts.total == decision.rate == Decimal("23.50")
    assert decision.limits.binding == "by_capacity"
    assert decision.triggers == ()
    trace = _trace(decision)
    assert trace["strategy.risk_matrix"][0] is False
    for rule in ("trigger.tax_arrears", "trigger.head_change", "limits.grade", "limits.group"):
        assert trace[rule][0] is False, rule


async def test_s2_ivanov_counter_offer_extends_the_term_then_cuts_the_amount() -> None:
    _, decision = await decide("s2_ivanov")
    assert decision.terms is not None
    assert Decimal("300000") <= decision.terms.amount < Decimal("5000000")
    assert decision.terms.term_months == 60
    assert decision.alternative_product_code == "OVERDRAFT"
    assert {ReasonCode.LIMIT_BY_REVENUE, ReasonCode.TERM_ADJUSTED} <= set(decision.reason_codes)
    # Обороты по выписке и грейд ограничивают слабее выручки и платёжеспособности.
    assert decision.limits.by_turnover is not None and decision.limits.by_grade is not None
    assert decision.limits.by_turnover > decision.limits.by_revenue
    assert _trace(decision)["trigger.turnover_spike"][0] is False


async def test_s3_vector_goes_to_a_person_by_registry_and_by_the_matrix() -> None:
    _, decision = await decide("s3_vector")
    assert set(decision.reason_codes) == {
        ReasonCode.ROUTE_VERIFICATION_MISMATCH,
        ReasonCode.ROUTE_RISK_MATRIX,
    }
    assert _trace(decision)["strategy.risk_matrix"] == (
        True,
        "грейд F (корзина F–G), сумма 10 000 000: автоматика до 5 000 000, ручная до "
        "20 000 000 → ручная проверка",
    )


async def test_s4_zakat_stops_before_the_strategy() -> None:
    _, decision = await decide("s4_zakat")
    assert decision.outcome == "REJECT"
    assert ReasonCode.STOP_RISK_MATRIX not in decision.reason_codes
    assert ReasonCode.STOP_GRADE_E not in decision.reason_codes
    assert "strategy.risk_matrix" not in _trace(decision)


async def test_s6_sboy_sources_failed_route_first() -> None:
    _, decision = await decide("s6_sboy")
    assert decision.reason_codes == (ReasonCode.ROUTE_SOURCES_FAILED,)
    assert decision.limits.by_group is None  # долг по БКИ неизвестен


@pytest.mark.parametrize("name", sorted(SCENARIOS))
async def test_client_texts_carry_no_internal_details(name: str) -> None:
    world, decision = await decide(name)
    texts = [decision.client_explanation, *decision.improvement_hints]
    for text in texts:
        assert text
        assert not any(code.value in text for code in ReasonCode)
        assert str(world.result.score) not in text
        for internal in ("скор", "грейд", "PD", "LGD", "LTV", "k(", "rule", "policy", "Контур"):
            assert internal not in text
