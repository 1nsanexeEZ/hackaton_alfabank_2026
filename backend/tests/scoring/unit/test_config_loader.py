"""Скоркарта грузится из YAML и валидируется: битый конфиг → ошибка (приложение не стартует)."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.modules.scoring.infrastructure.config_loader import (
    ScorecardConfigError,
    load_scorecard,
    load_scorecard_file,
)

_DEFAULT = (
    Path(__file__).resolve().parents[3]
    / "src/modules/scoring/infrastructure/config/scorecard_v1.yaml"
)
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
