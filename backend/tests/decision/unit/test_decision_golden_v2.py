"""Golden S-1…S-7 политики v2: те же заявки, но обогащение со всеми источниками — ГИР БО,
Контур, блокировки ФНС и БКИ руководителя (он дал согласие). Эталоны — в `golden_v2/`.

Что меняет v2 на демо: Закат получает стоп-факторы новых источников, у Сбоя не отвечает и БКИ
руководителя, у Вектора руководитель по реестру не найден среди участников — его БКИ не
запрашивается. Остальные исходы совпадают с v1.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from src.modules.decision.domain.model import PolicyDecision, ReasonCode
from src.modules.decision.infrastructure.config_loader import load_policy
from tests.decision.unit.decision_world import ALL_SOURCES, SCENARIOS, DecisionWorld, build_world
from tests.decision.unit.test_decision_golden import SCORECARD_V1, as_json

_GOLDEN = Path(__file__).resolve().parent / "golden_v2"
_KEY_RATE = Decimal("16.50")


async def decide(name: str, *, head_consent: bool = True) -> tuple[DecisionWorld, PolicyDecision]:
    world = await build_world(
        name, sources=ALL_SOURCES, head_consent=head_consent, scoring_model=SCORECARD_V1
    )
    policy = load_policy("policy_v2")
    collected = await world.builder(policy).collect(world.application_id)
    return world, policy.decide(collected.decision_input, key_rate=_KEY_RATE)


def _trace(decision: PolicyDecision) -> dict[str, tuple[bool, str]]:
    return {hit.rule: (hit.matched, hit.detail) for hit in decision.rule_trace}


@pytest.mark.parametrize("name", sorted(SCENARIOS))
async def test_scenario_matches_golden(name: str) -> None:
    world, decision = await decide(name)
    expected = json.loads((_GOLDEN / f"{name}.json").read_text(encoding="utf-8"))
    assert as_json(world, decision) == expected


@pytest.mark.parametrize(
    ("name", "outcome"),
    [
        ("s1_romashka", "APPROVE"),
        ("s2_ivanov", "COUNTER_OFFER"),
        ("s3_vector", "MANUAL_REVIEW"),
        ("s4_zakat", "REJECT"),
        ("s5a_progress", "REQUEST_INFO"),
        ("s5b_progress", "MANUAL_REVIEW"),
        ("s6_sboy", "MANUAL_REVIEW"),
        ("s7_romashka_mortgage", "MANUAL_REVIEW"),
    ],
)
async def test_outcomes_of_the_demo_stay(name: str, outcome: str) -> None:
    _, decision = await decide(name)
    assert decision.outcome == outcome
    assert decision.policy_version == "policy_v2"


async def test_s1_romashka_passes_every_new_check() -> None:
    _, decision = await decide("s1_romashka")
    trace = _trace(decision)
    for rule in (
        "stop.current_overdue",
        "stop.head_overdue",
        "stop.account_blocks",
        "stop.tax_arrears",
        "stop.bankruptcy_messages",
        "stop.enforcement",
        "stop.lawsuits",
        "stop.negative_equity",
        "stop.mass_address",
        "stop.okved",
        "route.tax_arrears",
    ):
        assert trace[rule][0] is False, rule
    assert trace["stop.head_overdue"][1] == "текущая просрочка руководителя 0 дн., порог ≥ 30"
    assert decision.reason_codes == ()


async def test_s4_zakat_stops_on_every_new_source() -> None:
    _, decision = await decide("s4_zakat")
    assert decision.outcome == "REJECT" and decision.terms is None
    assert set(decision.reason_codes) == {
        ReasonCode.STOP_LIQUIDATION,
        ReasonCode.STOP_OVERDUE_90,
        ReasonCode.STOP_CURRENT_OVERDUE,
        ReasonCode.STOP_HEAD_OVERDUE,
        ReasonCode.STOP_ACCOUNT_BLOCKS,
        ReasonCode.STOP_TAX_ARREARS,
        ReasonCode.STOP_LARGE_ENFORCEMENT,
        ReasonCode.STOP_LARGE_LAWSUITS,
        ReasonCode.STOP_NEGATIVE_EQUITY,
        ReasonCode.STOP_GRADE_E,
    }
    trace = _trace(decision)
    assert trace["stop.head_overdue"] == (
        True,
        "текущая просрочка руководителя 45 дн., порог ≥ 30",
    )
    assert trace["stop.negative_equity"] == (True, "собственный капитал за 2025: -2 400 000")


async def test_s4_zakat_without_the_head_consent_is_not_checked() -> None:
    _, decision = await decide("s4_zakat", head_consent=False)
    assert ReasonCode.STOP_HEAD_OVERDUE not in decision.reason_codes
    assert _trace(decision)["stop.head_overdue"] == (
        False,
        "нет согласия руководителя на запрос его БКИ — проверка не выполнена",
    )


async def test_s3_vector_has_no_registry_head_to_ask() -> None:
    _, decision = await decide("s3_vector")
    assert _trace(decision)["stop.head_overdue"] == (
        False,
        "руководитель по реестру не найден среди участников — проверка не выполнена",
    )


async def test_s6_sboy_routes_when_both_bureaus_fail() -> None:
    _, decision = await decide("s6_sboy")
    assert decision.reason_codes == (ReasonCode.ROUTE_SOURCES_FAILED,)
    assert _trace(decision)["route.bureau_unavailable"] == (
        True,
        "не ответили источники: bki, bki_head",
    )


@pytest.mark.parametrize("name", sorted(SCENARIOS))
async def test_client_texts_carry_no_internal_details(name: str) -> None:
    world, decision = await decide(name)
    texts = [decision.client_explanation, *decision.improvement_hints]
    for text in texts:
        assert text
        assert not any(code.value in text for code in ReasonCode)
        assert str(world.result.score) not in text
        for internal in ("скор", "грейд", "LTV", "k(", "rule", "policy", "Контур", "ГИР БО"):
            assert internal not in text
