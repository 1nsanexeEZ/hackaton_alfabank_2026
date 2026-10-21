"""Загрузка скоркарты из YAML с валидацией Pydantic.

Карта — данные, а не код: баллы корзин, база и пороги грейдов живут в
`config/scorecard_v1.yaml`. Файл проверяется при старте; невалидный YAML (нет фактора, корзины
или не то число) → `ScorecardConfigError`, и приложение не стартует — лучше сразу, чем молча
посчитать не так.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError

from src.scoring.domain.scorecard import Scorecard, ScorecardConfig

_CONFIG_DIR = Path(__file__).resolve().parent / "config"
_DEFAULT_CARD = "scorecard_v1"

# Фактор → обязательные корзины (должны совпадать с логикой в domain/scorecard.py).
_REQUIRED_BUCKETS: dict[str, frozenset[str]] = {
    "business_age": frozenset({"lt12", "m12_24", "m24_60", "gt60"}),
    "revenue_trend": frozenset({"down20", "down0", "up20", "up_more"}),
    "debt_load": frozenset({"lt02", "lt04", "lt06", "gt06"}),
    "bureau_overdue": frozenset({"none", "d1_30", "d31_90", "d90_plus", "thin"}),
    "bureau_inquiries": frozenset({"le2", "i3_5", "gt5"}),
    "tax_arrears": frozenset({"none", "any"}),
    "industry_risk": frozenset({"low", "mid", "high"}),
    "amount_to_revenue": frozenset({"lt01", "lt03", "lt05", "gt05"}),
    "revenue_consistency": frozenset({"le15", "p15_30", "gt30"}),
    "verification": frozenset({"verified", "mismatch", "other"}),
    "collateral_coverage": frozenset({"ge2", "c1_2", "lt1"}),
    "cash_gap": frozenset({"gap", "no_gap"}),
}
_REQUIRED_GRADES = frozenset({"A", "B", "C", "D"})


class ScorecardConfigError(Exception):
    """Скоркарта в YAML не прошла валидацию — приложение не должно стартовать."""


class _Schema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    base: int
    grades: dict[str, int]
    industry_sections: dict[str, list[int]]
    factors: dict[str, dict[str, int]]


def load_scorecard(name: str = _DEFAULT_CARD) -> Scorecard:
    return load_scorecard_file(_CONFIG_DIR / f"{name}.yaml")


def load_scorecard_file(path: Path) -> Scorecard:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ScorecardConfigError(f"Не удалось прочитать скоркарту {path}: {exc}") from exc
    try:
        schema = _Schema.model_validate(raw)
    except ValidationError as exc:
        raise ScorecardConfigError(f"Скоркарта {path} не прошла схему: {exc}") from exc
    _check_completeness(schema, path)
    return Scorecard(
        ScorecardConfig(
            version=schema.version,
            base=schema.base,
            grades=dict(schema.grades),
            points={factor: dict(buckets) for factor, buckets in schema.factors.items()},
            industry_low=frozenset(schema.industry_sections.get("low", [])),
            industry_high=frozenset(schema.industry_sections.get("high", [])),
        )
    )


@lru_cache(maxsize=4)
def default_scorecard() -> Scorecard:
    """Карта по умолчанию, загружается один раз на процесс."""
    return load_scorecard()


def _check_completeness(schema: _Schema, path: Path) -> None:
    missing_grades = _REQUIRED_GRADES - schema.grades.keys()
    if missing_grades:
        raise ScorecardConfigError(
            f"Скоркарта {path}: нет порогов грейдов {sorted(missing_grades)}"
        )
    for factor, required in _REQUIRED_BUCKETS.items():
        buckets = schema.factors.get(factor)
        if buckets is None:
            raise ScorecardConfigError(f"Скоркарта {path}: нет фактора {factor!r}")
        missing = required - buckets.keys()
        if missing:
            raise ScorecardConfigError(
                f"Скоркарта {path}: у фактора {factor!r} нет корзин {sorted(missing)}"
            )
    for section in ("low", "high"):
        if section not in schema.industry_sections:
            raise ScorecardConfigError(f"Скоркарта {path}: нет секции industry_sections.{section}")
