"""Скоркарта грузится из YAML и валидируется: битый конфиг → ошибка (приложение не стартует)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

from src.modules.scoring.infrastructure.config_loader import (
    ScorecardConfigError,
    load_pd_model_file,
    load_scorecard,
    load_scorecard_file,
)

_CONFIG = Path(__file__).resolve().parents[3] / "src/modules/scoring/infrastructure/config"
_DEFAULT = _CONFIG / "scorecard_v1.yaml"
_VALID = _DEFAULT.read_text(encoding="utf-8")


def test_default_card_loads() -> None:
    card = load_scorecard()
    assert card.version == "scorecard_v1"


def test_missing_factor_rejected(tmp_path: Path) -> None:
    # Убираем корзины cash_gap — фактор остаётся без значений (невалидно).
    broken = _VALID.replace("    gap: -15\n    no_gap: 10\n", "")
    path = tmp_path / "broken.yaml"
    path.write_text(broken, encoding="utf-8")
    with pytest.raises(ScorecardConfigError, match="cash_gap"):
        load_scorecard_file(path)


def test_missing_bucket_rejected(tmp_path: Path) -> None:
    broken = _VALID.replace("    gt60: 50\n", "")
    path = tmp_path / "broken.yaml"
    path.write_text(broken, encoding="utf-8")
    with pytest.raises(ScorecardConfigError, match="business_age"):
        load_scorecard_file(path)


def test_missing_grade_rejected(tmp_path: Path) -> None:
    broken = _VALID.replace("  A: 750\n", "")
    path = tmp_path / "broken.yaml"
    path.write_text(broken, encoding="utf-8")
    with pytest.raises(ScorecardConfigError):
        load_scorecard_file(path)


def test_wrong_type_rejected(tmp_path: Path) -> None:
    broken = _VALID.replace("base: 600", "base: not-a-number")
    path = tmp_path / "broken.yaml"
    path.write_text(broken, encoding="utf-8")
    with pytest.raises(ScorecardConfigError):
        load_scorecard_file(path)


def test_absent_file_rejected(tmp_path: Path) -> None:
    with pytest.raises(ScorecardConfigError):
        load_scorecard_file(tmp_path / "nope.yaml")


# --- PD-модель ---------------------------------------------------------------------------


def _model(tmp_path: Path, breaks: Callable[[dict[str, Any]], None] | None = None) -> Path:
    raw = yaml.safe_load((_CONFIG / "pd_model_v2.yaml").read_text(encoding="utf-8"))
    if breaks is not None:
        breaks(raw)
    path = tmp_path / "model.yaml"
    path.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    return path


def _le(raw: dict[str, Any]) -> dict[str, Any]:
    features: dict[str, Any] = raw["scorecards"]["legal_entity"]["features"]
    return features


def test_shipped_model_roundtrips(tmp_path: Path) -> None:
    model = load_pd_model_file(_model(tmp_path))
    assert model.version == "pd_model_v2"
    assert set(model.config.scorecards) == {"legal_entity", "entrepreneur", "new_client"}


@pytest.mark.parametrize(
    ("breaks", "message"),
    [
        (lambda m: m["scorecards"].pop("new_client"), "скоркарты сегментов"),
        (lambda m: m["grades"].pop("I"), "границы PD"),
        (lambda m: m["grades"].update({"B": "0.001"}), "должны расти"),
        (lambda m: _le(m).update({"magic": _le(m)["cash_gap"]}), "неизвестные признаки"),
        (lambda m: _le(m).pop("debt_load"), "нет признаков"),
        (lambda m: _le(m)["tax_arrears"]["bins"].pop(), "категорий"),
        (lambda m: _le(m)["debt_load"]["bins"].pop(1), "дырка или перекрытие"),
        (lambda m: _le(m)["debt_load"]["bins"].pop(), "не покрывают значения от"),
        (lambda m: _le(m)["business_age"]["bins"][0].update({"from": "1"}), "ниже"),
        (
            lambda m: _le(m)["verification"]["bins"].append(
                {"label": "x", "to": "1", "woe": "0", "points": 0}
            ),
            "интервальные",
        ),
        (lambda m: m["scorecards"]["legal_entity"]["calibration"].update({"pdo": 0}), "схему"),
    ],
)
def test_broken_model_is_rejected(
    tmp_path: Path, breaks: Callable[[dict[str, Any]], None], message: str
) -> None:
    with pytest.raises(ScorecardConfigError, match=message):
        load_pd_model_file(_model(tmp_path, breaks))
