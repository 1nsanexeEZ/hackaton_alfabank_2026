"""Golden S-1…S-7 политики v1: заявка из демо §9 → решение, эталон в JSON рядом.

Версия политики закреплена: v1 решает на ЕГРЮЛ, ФНС и БКИ, как в момент её выхода. Golden
следующей версии — в `test_decision_golden_v2.py`.

Поменялась политика или тексты — golden-файлы покажут, какие сценарии и как сдвинулись.
Отдельно закреплены исходы из таблицы сценариев и грейды скоринга, на которых они стоят.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from src.modules.decision.domain.model import PolicyDecision, ReasonCode
from src.modules.decision.infrastructure.config_loader import load_policy
from tests.decision.unit.decision_world import SCENARIOS, DecisionWorld, build_world

_GOLDEN = Path(__file__).resolve().parent / "golden"
_KEY_RATE = Decimal("16.50")


async def decide(name: str) -> tuple[DecisionWorld, PolicyDecision]:
    world = await build_world(name)
    policy = load_policy("policy_v1")
    collected = await world.builder(policy).collect(world.application_id)
    return world, policy.decide(collected.decision_input, key_rate=_KEY_RATE)


def as_json(world: DecisionWorld, decision: PolicyDecision) -> dict[str, Any]:
    def plain(value: Any) -> Any:
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, dict):
            return {k: plain(v) for k, v in value.items()}
        if isinstance(value, list | tuple):
            return [plain(v) for v in value]
        return value

    data = asdict(decision)
    data["reason_codes"] = [str(code) for code in decision.reason_codes]
    data["scoring"] = {
        "score": world.result.score,
        "grade": world.result.grade,
        "flags": list(world.result.flags),
    }
    return plain(data)


@pytest.mark.parametrize("name", sorted(SCENARIOS))
async def test_scenario_matches_golden(name: str) -> None:
    world, decision = await decide(name)
    expected = json.loads((_GOLDEN / f"{name}.json").read_text(encoding="utf-8"))
    assert as_json(world, decision) == expected


# Грейды и флаги скоринга, на которых стоят исходы (совпадают со сквозными тестами #41).
@pytest.mark.parametrize(
    ("name", "score", "grade", "flags"),
    [
        ("s1_romashka", 790, "A", ()),
        ("s2_ivanov", 565, "C", ("thin_file", "cash_gap")),
        ("s3_vector", 620, "C", ("verification_mismatch",)),
        ("s4_zakat", 395, "E", ()),
        ("s5a_progress", 700, "B", ("revenue_mismatch",)),
        ("s6_sboy", 760, "A", ("bureau_unavailable",)),
        ("s7_romashka_mortgage", 700, "B", ()),
    ],
)
async def test_world_scores_like_scoring_golden(
    name: str, score: int, grade: str, flags: tuple[str, ...]
) -> None:
    world = await build_world(name)
    assert (world.result.score, world.result.grade, world.result.flags) == (score, grade, flags)


async def test_s1_romashka_approved_as_requested() -> None:
    _, decision = await decide("s1_romashka")
    assert decision.outcome == "APPROVE"
    assert decision.terms is not None
    assert (decision.terms.amount, decision.terms.term_months) == (Decimal("3000000"), 24)
    assert decision.reason_codes == ()
    assert decision.alternative_product_code is None


async def test_s2_ivanov_counter_offer_with_overdraft_for_cash_gap() -> None:
    _, decision = await decide("s2_ivanov")
    assert decision.outcome == "COUNTER_OFFER"
    assert decision.terms is not None
    assert Decimal("300000") <= decision.terms.amount < Decimal("5000000")
    assert decision.terms.amount % 10000 == 0
    assert decision.alternative_product_code == "OVERDRAFT"
    assert {ReasonCode.LIMIT_BY_REVENUE, ReasonCode.LIMIT_BY_PAYMENT_CAPACITY} & set(
        decision.reason_codes
    )
    assert ReasonCode.CASH_GAP_FORECAST in decision.reason_codes
    assert "кассовый разрыв в ноябре 2026, для него удобнее овердрафт" in (
        decision.client_explanation
    )
    assert any("кассового разрыва" in c for c in decision.terms.conditions)
    # Банк видит, почему именно эта сумма: все три лимита в решении.
    assert decision.limits.by_revenue is not None and decision.limits.by_capacity is not None


async def test_s3_vector_manual_review_on_registry_mismatch() -> None:
    _, decision = await decide("s3_vector")
    assert decision.outcome == "MANUAL_REVIEW"
    assert decision.reason_codes == (ReasonCode.ROUTE_VERIFICATION_MISMATCH,)


async def test_s4_zakat_rejected_on_stop_factors() -> None:
    _, decision = await decide("s4_zakat")
    assert decision.outcome == "REJECT"
    assert {ReasonCode.STOP_LIQUIDATION, ReasonCode.STOP_OVERDUE_90} <= set(decision.reason_codes)
    assert decision.alternative_product_code is None
    assert decision.terms is None


async def test_s5_progress_requests_statement_then_goes_to_underwriter() -> None:
    _, first = await decide("s5a_progress")
    assert first.outcome == "REQUEST_INFO"
    assert first.reason_codes == (ReasonCode.INFO_REVENUE_NOT_CONFIRMED,)
    assert first.requested_info is not None
    assert first.requested_info.documents == ("bank_statement",)
    assert "выпиской по счёту за 6 месяцев" in first.requested_info.comment

    _, second = await decide("s5b_progress")
    assert second.outcome == "MANUAL_REVIEW"
    assert ReasonCode.ROUTE_REVENUE_MISMATCH in second.reason_codes


async def test_s6_sboy_manual_review_when_bureau_fails() -> None:
    _, decision = await decide("s6_sboy")
    assert decision.outcome == "MANUAL_REVIEW"
    assert decision.reason_codes == (ReasonCode.ROUTE_SOURCES_FAILED,)


async def test_s7_mortgage_always_manual_review() -> None:
    _, decision = await decide("s7_romashka_mortgage")
    assert decision.outcome == "MANUAL_REVIEW"
    assert decision.reason_codes == (ReasonCode.ROUTE_AMOUNT_OVER_AUTO_LIMIT,)
    # Лимиты посчитаны и для ручного решения — андеррайтер видит LTV и платёжеспособность.
    assert decision.limits.by_ltv == Decimal("35000000.00")


@pytest.mark.parametrize("name", sorted(SCENARIOS))
async def test_client_texts_carry_no_internal_details(name: str) -> None:
    world, decision = await decide(name)
    texts = [decision.client_explanation, *decision.improvement_hints]
    if decision.requested_info is not None:
        texts.append(decision.requested_info.comment)
    for text in texts:
        assert text
        assert not any(code.value in text for code in ReasonCode)
        assert str(world.result.score) not in text
        for internal in ("скор", "грейд", "LTV", "k(", "rule", "policy"):
            assert internal not in text
