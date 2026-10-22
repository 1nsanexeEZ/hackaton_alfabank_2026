"""Golden-тесты PD-модели: фиксированный вход (§9) → сегмент, балл, PD, грейд, причины и признаки
из JSON в `golden_v2/`. Поменялась модель — golden-файлы покажут, какие сценарии сдвинулись.
Golden scorecard_v1 — в test_scorecard_golden.py, они остаются как были."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.modules.scoring.infrastructure.config_loader import load_pd_model
from src.modules.scoring.infrastructure.repository import _factor_to_json
from tests.scoring.scenarios import SCENARIOS

_GOLDEN = Path(__file__).resolve().parents[1] / "golden_v2"
_MODEL = load_pd_model("pd_model_v2")


def actual(name: str) -> dict[str, Any]:
    output = _MODEL.calculate(SCENARIOS[name])
    return {
        "segment": output.segment,
        "scorecard": output.scorecard,
        "score": output.score,
        "pd_12m": str(output.pd_12m),
        "grade": output.grade,
        "reason_codes": list(output.reason_codes),
        "data_completeness": str(output.data_completeness),
        "flags": list(output.flags),
        "bank_notes": list(output.bank_notes),
        "factors": [_factor_to_json(f) for f in output.factors],
    }


@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_scenario_matches_golden(name: str) -> None:
    expected = json.loads((_GOLDEN / f"{name}.json").read_text(encoding="utf-8"))
    assert actual(name) == expected


# Якоря калибровки: на них стоят исходы демо в policy_v3.
@pytest.mark.parametrize(
    ("name", "segment", "grade"),
    [
        ("romashka_s1", "legal_entity", "A"),
        ("ivanov_s2", "entrepreneur", "E"),
        ("vector_s3", "legal_entity", "F"),
        ("zakat_s4", "legal_entity", "J"),
        ("progress_s5", "legal_entity", "C"),
        ("sboy_s6", "legal_entity", "B"),
        ("romashka_mortgage_s7", "legal_entity", "C"),
    ],
)
def test_calibration_anchors(name: str, segment: str, grade: str) -> None:
    output = _MODEL.calculate(SCENARIOS[name])
    assert (output.segment, output.grade) == (segment, grade)
