"""Загрузка ML-модели из YAML с валидацией Pydantic.

Файл `config/ml_logreg_v1.yaml` пишет скрипт обучения (`backend/ml/train.py`): корзины, WoE,
коэффициенты, масштаб скора и границы грейдов A–I по PD (выше I — J, как у PD-модели).
Невалидный файл → `MlConfigError`, приложение не стартует, как и с PD-моделью.
"""

from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError

from src.modules.scoring.domain.ml_model import (
    FeatureSpec,
    IndustrySections,
    MlConfig,
    MlModel,
    NumericBin,
)

_CONFIG_DIR = Path(__file__).resolve().parent / "config"
_DEFAULT_MODEL = "ml_logreg_v1"
_FEATURES = frozenset(
    {
        "business_age_months",
        "revenue_growth",
        "debt_service_ratio",
        "amount_to_revenue",
        "revenue_gap",
        "bureau_overdue",
        "bureau_inquiries",
        "tax_arrears",
        "verification",
        "industry_risk",
        "cash_gap",
        "revenue_confirmed",
        "collateral_coverage",
    }
)


class MlConfigError(Exception):
    """Конфиг ML-модели не прошёл валидацию — приложение не должно стартовать."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Bin(_Strict):
    upper: Decimal | None
    woe: Decimal
    label: str


class _Feature(_Strict):
    name: str
    title: str
    kind: Literal["numeric", "category"]
    coef: Decimal
    missing_woe: Decimal
    bins: list[_Bin] = []
    categories: dict[str, Decimal] = {}


class _Scaling(_Strict):
    base_score: Decimal
    base_odds: Decimal
    pdo: Decimal


class _Band(_Strict):
    grade: Literal["A", "B", "C", "D", "E", "F", "G", "H", "I"]
    max_pd: Decimal


class _IndustrySections(_Strict):
    low: list[int]
    high: list[int]


class _Schema(_Strict):
    version: str
    intercept: Decimal
    scaling: _Scaling
    grade_bands: list[_Band]
    industry_sections: _IndustrySections
    features: list[_Feature]
    metadata: dict[str, Any] = {}


def load_ml_model(name: str = _DEFAULT_MODEL) -> MlModel:
    return load_ml_model_file(_CONFIG_DIR / f"{name}.yaml")


def load_ml_model_file(path: Path) -> MlModel:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise MlConfigError(f"Не удалось прочитать ML-модель {path}: {exc}") from exc
    try:
        schema = _Schema.model_validate(raw)
    except ValidationError as exc:
        raise MlConfigError(f"ML-модель {path} не прошёл схему: {exc}") from exc
    _check(schema, path)
    return MlModel(
        MlConfig(
            version=schema.version,
            intercept=schema.intercept,
            features=tuple(_feature(f) for f in schema.features),
            base_score=schema.scaling.base_score,
            base_odds=schema.scaling.base_odds,
            pdo=schema.scaling.pdo,
            grade_bands=tuple((band.grade, band.max_pd) for band in schema.grade_bands),
            industry=IndustrySections(
                low=frozenset(schema.industry_sections.low),
                high=frozenset(schema.industry_sections.high),
            ),
        )
    )


@lru_cache(maxsize=4)
def default_ml_model() -> MlModel:
    return load_ml_model()


def _feature(raw: _Feature) -> FeatureSpec:
    return FeatureSpec(
        name=raw.name,
        title=raw.title,
        kind=raw.kind,
        coef=raw.coef,
        missing_woe=raw.missing_woe,
        bins=tuple(NumericBin(upper=b.upper, woe=b.woe, label=b.label) for b in raw.bins),
        categories=tuple(raw.categories.items()),
    )


def _check(schema: _Schema, path: Path) -> None:
    names = [f.name for f in schema.features]
    unknown = set(names) - _FEATURES
    if unknown:
        raise MlConfigError(f"ML-модель {path}: неизвестные признаки {sorted(unknown)}")
    if len(names) != len(set(names)):
        raise MlConfigError(f"ML-модель {path}: признаки повторяются")
    for feature in schema.features:
        if feature.kind == "numeric":
            if not feature.bins or feature.bins[-1].upper is not None:
                raise MlConfigError(
                    f"ML-модель {path}: у {feature.name!r} последняя корзина должна быть открытой"
                )
            uppers = [b.upper for b in feature.bins[:-1]]
            if any(u is None for u in uppers) or uppers != sorted(uppers):  # type: ignore[type-var]
                raise MlConfigError(
                    f"ML-модель {path}: у {feature.name!r} границы корзин не по возрастанию"
                )
        elif not feature.categories:
            raise MlConfigError(f"ML-модель {path}: у {feature.name!r} нет категорий")
    bands = [band.max_pd for band in schema.grade_bands]
    if [band.grade for band in schema.grade_bands] != list("ABCDEFGHI") or bands != sorted(bands):
        raise MlConfigError(f"ML-модель {path}: границы грейдов A–I по возрастанию PD")
    sections = schema.industry_sections
    if not sections.low or not sections.high or set(sections.low) & set(sections.high):
        raise MlConfigError(
            f"ML-модель {path}: industry_sections — непустые low и high без общих секций"
        )
