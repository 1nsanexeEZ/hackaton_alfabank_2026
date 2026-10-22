"""Golden-тесты скоркарты: фиксированный вход (§9) → ожидаемый результат из JSON рядом.

Поменялась карта или логика фактора — golden-файлы покажут, какие сценарии сдвинулись.
Отдельно закреплены якоря калибровки (romashka → A, ivanov → C и т.д.).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.modules.scoring.infrastructure.config_loader import load_scorecard
from src.modules.scoring.infrastructure.repository import _factor_to_json
from tests.scoring.scenarios import SCENARIOS

_GOLDEN = Path(__file__).resolve().parents[1] / "golden"
_CARD = load_scorecard()


def _actual(name: str) -> dict[str, Any]:
    output = _CARD.calculate(SCENARIOS[name])
    return {
        "score": output.score,
        "grade": output.grade,
        "data_completeness": str(output.data_completeness),
        "flags": list(output.flags),
        "bank_notes": list(output.bank_notes),
        "factors": [_factor_to_json(f) for f in output.factors],
    }


@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_scenario_matches_golden(name: str) -> None:
    expected = json.loads((_GOLDEN / f"{name}.json").read_text(encoding="utf-8"))
    assert _actual(name) == expected


def test_romashka_is_grade_a() -> None:
    output = _CARD.calculate(SCENARIOS["romashka_s1"])
    assert output.score == 790
    assert output.grade == "A"
    assert output.flags == ()


def test_ivanov_counteroffer_grade_with_cash_gap() -> None:
    output = _CARD.calculate(SCENARIOS["ivanov_s2"])
    assert output.grade == "C"  # не уходит в ручную — остаётся кандидатом на встречное предложение
    assert "cash_gap" in output.flags
    assert output.bank_notes and "кассовый разрыв" in output.bank_notes[0]


def test_zakat_is_worst_grade() -> None:
    assert _CARD.calculate(SCENARIOS["zakat_s4"]).grade == "E"


def test_progress_flags_revenue_mismatch() -> None:
    assert "revenue_mismatch" in _CARD.calculate(SCENARIOS["progress_s5"]).flags


def test_vector_flags_verification_mismatch() -> None:
    assert "verification_mismatch" in _CARD.calculate(SCENARIOS["vector_s3"]).flags


def test_sboy_flags_bureau_unavailable_not_penalized() -> None:
    output = _CARD.calculate(SCENARIOS["sboy_s6"])
    assert "bureau_unavailable" in output.flags
    # Сбой источника не роняет оценку: бюро-факторы нейтральны.
    bureau = {f.code: f for f in output.factors}
    assert bureau["bureau_overdue"].direction == "neutral"
    assert bureau["bureau_inquiries"].direction == "neutral"


def test_mortgage_has_collateral_factor() -> None:
    codes = {f.code for f in _CARD.calculate(SCENARIOS["romashka_mortgage_s7"]).factors}
    assert "collateral_coverage" in codes
