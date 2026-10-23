"""ML-модель: паритет с обучением, golden демо-сценариев, общая с PD-моделью шкала грейдов,
поведение на краях, загрузчик."""

from __future__ import annotations

import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import yaml

from src.modules.scoring.application.serialization import load_input
from src.modules.scoring.domain.ml_model import ml_features
from src.modules.scoring.infrastructure.config_loader import load_pd_model
from src.modules.scoring.infrastructure.ml_loader import (
    _FEATURES,
    MlConfigError,
    load_ml_model,
    load_ml_model_file,
)
from tests.scoring.scenarios import SCENARIOS

_BACKEND = Path(__file__).resolve().parents[3]
_FIXTURE = _BACKEND / "tests/scoring/fixtures/ml_parity.json"
_CONFIG = _BACKEND / "src/modules/scoring/infrastructure/config/ml_logreg_v1.yaml"
_MODEL = load_ml_model()

# PD и грейд ML-модели на демо-сценариях §9 (входы — из golden scoring).
_GOLDEN = {
    "romashka_s1": ("0.0139", "C"),
    "ivanov_s2": ("0.0275", "E"),
    "vector_s3": ("0.0429", "F"),
    "zakat_s4": ("0.2369", "J"),
    "progress_s5": ("0.0425", "F"),
    "sboy_s6": ("0.0116", "C"),
    "romashka_mortgage_s7": ("0.0245", "D"),
}


def test_inference_matches_training_export() -> None:
    """Прод считает ровно то, что обучение выгрузило (200 заявок тестовой выборки)."""
    data = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    assert data["model"] == _MODEL.version
    for row in data["rows"]:
        result = _MODEL.predict(load_input(row["input"]))
        assert (str(result.pd_12m), result.score, result.grade, list(result.reason_codes)) == (
            row["pd_12m"],
            row["score"],
            row["grade"],
            row["reason_codes"],
        )


@pytest.mark.parametrize("name", sorted(_GOLDEN))
def test_demo_scenarios_golden(name: str) -> None:
    result = _MODEL.predict(SCENARIOS[name])
    assert (str(result.pd_12m), result.grade) == _GOLDEN[name]


def test_grades_on_the_scale_of_the_pd_model() -> None:
    """Границы грейдов A–I — те же, что у PD-модели: админ сравнивает грейды напрямую."""
    assert _MODEL.config.grade_bands == load_pd_model().config.grades


def test_higher_score_means_lower_pd() -> None:
    results = sorted((_MODEL.predict(inp) for inp in SCENARIOS.values()), key=lambda r: r.score)
    pds = [r.pd_12m for r in results]
    assert pds == sorted(pds, reverse=True)


def test_overdue_raises_pd() -> None:
    base = SCENARIOS["romashka_s1"]
    worse = replace(base, bureau=replace(base.bureau, max_overdue_days_12m=120))
    assert _MODEL.predict(worse).pd_12m > _MODEL.predict(base).pd_12m


def test_debt_load_raises_pd() -> None:
    base = SCENARIOS["romashka_s1"]
    worse = replace(base, bureau=replace(base.bureau, total_monthly_payments=Decimal("2500000")))
    assert _MODEL.predict(worse).pd_12m > _MODEL.predict(base).pd_12m


def test_missing_bureau_uses_missing_bin() -> None:
    factors = {f.code: f for f in _MODEL.predict(SCENARIOS["sboy_s6"]).factors}  # БКИ нет
    inquiries = factors["bureau_inquiries"]
    assert inquiries.value is None and inquiries.has_data is False
    assert inquiries.bin == "нет данных"


def test_worst_factor_explains_zakat() -> None:
    result = _MODEL.predict(SCENARIOS["zakat_s4"])
    assert result.reason_codes[0] == "bureau_overdue"  # просрочка 120 дней — главный вклад
    worst = min(result.factors, key=lambda f: f.points)
    assert worst.code == "bureau_overdue" and worst.direction == "negative"


def test_loader_knows_every_feature_of_the_function() -> None:
    assert set(ml_features(SCENARIOS["romashka_s1"])) == _FEATURES


def _broken(tmp_path: Path, change: Any) -> Path:
    config = yaml.safe_load(_CONFIG.read_text(encoding="utf-8"))
    change(config)
    path = tmp_path / "broken.yaml"
    path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")
    return path


def test_unknown_feature_rejected(tmp_path: Path) -> None:
    def rename(config: dict[str, Any]) -> None:
        config["features"][0]["name"] = "favourite_colour"

    with pytest.raises(MlConfigError, match="неизвестные признаки"):
        load_ml_model_file(_broken(tmp_path, rename))


def test_closed_last_bin_rejected(tmp_path: Path) -> None:
    def close(config: dict[str, Any]) -> None:
        numeric = next(f for f in config["features"] if f["kind"] == "numeric")
        numeric["bins"][-1]["upper"] = "999"

    with pytest.raises(MlConfigError, match="последняя корзина"):
        load_ml_model_file(_broken(tmp_path, close))


def test_unordered_grade_bands_rejected(tmp_path: Path) -> None:
    def swap(config: dict[str, Any]) -> None:
        bands = config["grade_bands"]
        bands[0]["max_pd"], bands[1]["max_pd"] = bands[1]["max_pd"], bands[0]["max_pd"]

    with pytest.raises(MlConfigError, match="грейдов"):
        load_ml_model_file(_broken(tmp_path, swap))


def test_absent_file_rejected(tmp_path: Path) -> None:
    with pytest.raises(MlConfigError):
        load_ml_model_file(tmp_path / "nope.yaml")
