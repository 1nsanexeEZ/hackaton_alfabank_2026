"""Загрузка скоркарты и PD-модели из YAML с валидацией Pydantic.

Модель — данные, а не код: баллы корзин, база и пороги грейдов scorecard_v1 живут в
`config/scorecard_v1.yaml`, сегменты, бины, WoE, калибровка и шкала A–J действующей модели — в
`config/pd_model_v2.yaml`. Файлы проверяются при старте; невалидный YAML (нет признака, бина,
бины с дыркой или не то число) → `ScorecardConfigError`, и приложение не стартует — лучше сразу,
чем молча посчитать не так.
"""

from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any, get_args

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src.modules.enrichment.facade import Source
from src.modules.scoring.domain.features import FEATURES
from src.modules.scoring.domain.model import Grade, Segment
from src.modules.scoring.domain.pd_model import (
    BinSpec,
    Calibration,
    FeatureSpec,
    PdModel,
    PdModelConfig,
    ScorecardSpec,
)
from src.modules.scoring.domain.prescreen import FounderPrescreen, PrescreenConfig
from src.modules.scoring.domain.project import ProjectAssessment, ProjectConfig
from src.modules.scoring.domain.quality import QualityPolicy
from src.modules.scoring.domain.scorecard import Scorecard, ScorecardConfig

_CONFIG_DIR = Path(__file__).resolve().parent / "config"
_DEFAULT_CARD = "scorecard_v1"
_DEFAULT_MODEL = "pd_model_v2"
_DEFAULT_PRESCREEN = "prescreen_v1"
_DEFAULT_QUALITY = "quality_v1"
_DEFAULT_PROJECT = "project_v1"

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


# --- предскрин учредителя ----------------------------------------------------------------------


class _PrescreenSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    current_overdue_days: int = Field(ge=1)
    max_overdue_days_12m: int = Field(ge=0)
    inquiries_30d: int = Field(ge=0)
    monthly_payments: Decimal = Field(gt=0)


def load_prescreen(name: str = _DEFAULT_PRESCREEN) -> FounderPrescreen:
    return load_prescreen_file(_CONFIG_DIR / f"{name}.yaml")


def load_prescreen_file(path: Path) -> FounderPrescreen:
    try:
        raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ScorecardConfigError(f"Не удалось прочитать предскрин {path}: {exc}") from exc
    try:
        schema = _PrescreenSchema.model_validate(raw)
    except ValidationError as exc:
        raise ScorecardConfigError(f"Предскрин {path} не прошёл схему: {exc}") from exc
    return FounderPrescreen(PrescreenConfig(**schema.model_dump()))


@lru_cache(maxsize=4)
def default_prescreen() -> FounderPrescreen:
    return load_prescreen()


# --- проектная оценка стартапа ----------------------------------------------------------------


class _ProjectSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    horizon_months: int = Field(ge=1)
    min_dscr: Decimal = Field(gt=0)
    min_own_share: Decimal = Field(ge=0, lt=1)
    min_coverage: Decimal = Field(ge=0)
    collateral_discount: Decimal = Field(gt=0, le=1)
    max_guarantee_share: Decimal = Field(ge=0, le=1)
    industry_high_sections: list[int]


def load_project(name: str = _DEFAULT_PROJECT) -> ProjectAssessment:
    return load_project_file(_CONFIG_DIR / f"{name}.yaml")


def load_project_file(path: Path) -> ProjectAssessment:
    try:
        raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ScorecardConfigError(f"Не удалось прочитать проектную оценку {path}: {exc}") from exc
    try:
        schema = _ProjectSchema.model_validate(raw)
    except ValidationError as exc:
        raise ScorecardConfigError(f"Проектная оценка {path} не прошла схему: {exc}") from exc
    return ProjectAssessment(
        ProjectConfig(
            version=schema.version,
            horizon_months=schema.horizon_months,
            min_dscr=schema.min_dscr,
            min_own_share=schema.min_own_share,
            collateral_discount=schema.collateral_discount,
            max_guarantee_share=schema.max_guarantee_share,
            min_coverage=schema.min_coverage,
            industry_high=frozenset(schema.industry_high_sections),
        )
    )


@lru_cache(maxsize=4)
def default_project() -> ProjectAssessment:
    return load_project()


# --- качество данных ---------------------------------------------------------------------------


class _QualitySchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    critical_sources: list[str]
    min_completeness: Decimal = Field(ge=0, le=1)


def load_quality(name: str = _DEFAULT_QUALITY) -> QualityPolicy:
    return load_quality_file(_CONFIG_DIR / f"{name}.yaml")


def load_quality_file(path: Path) -> QualityPolicy:
    try:
        raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ScorecardConfigError(f"Не удалось прочитать качество данных {path}: {exc}") from exc
    try:
        schema = _QualitySchema.model_validate(raw)
    except ValidationError as exc:
        raise ScorecardConfigError(f"Качество данных {path} не прошло схему: {exc}") from exc
    unknown = set(schema.critical_sources) - set(get_args(Source))
    if unknown:
        raise ScorecardConfigError(f"{path}: неизвестные источники {sorted(unknown)}")
    return QualityPolicy(
        version=schema.version,
        critical_sources=frozenset(schema.critical_sources),
        min_completeness=schema.min_completeness,
    )


@lru_cache(maxsize=4)
def default_quality() -> QualityPolicy:
    return load_quality()


# --- PD-модель ---------------------------------------------------------------------------------

_SEGMENTS: frozenset[Segment] = frozenset({"legal_entity", "entrepreneur", "new_client"})
_PD_GRADES: tuple[Grade, ...] = ("A", "B", "C", "D", "E", "F", "G", "H", "I")
# Категории, которые отдают признаки (features.py): у каждой должен быть бин.
_CATEGORIES: dict[str, frozenset[str]] = {
    "bureau_overdue": frozenset({"thin"}),
    "tax_arrears": frozenset({"none", "any"}),
    "industry_risk": frozenset({"low", "mid", "high"}),
    "verification": frozenset({"verified", "mismatch", "other"}),
    "cash_gap": frozenset({"gap", "no_gap"}),
}
_NUMERIC = frozenset(FEATURES) - {"tax_arrears", "industry_risk", "verification", "cash_gap"}
# Без этих признаков скоркарта не опишет заёмщика; остальные — по сегменту.
_REQUIRED_FEATURES = frozenset(
    {"business_age", "debt_load", "bureau_overdue", "amount_to_revenue", "collateral_coverage"}
)


class _Bin(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    label: str = Field(min_length=1)
    woe: Decimal
    points: int
    category: str | None = None
    lower: Decimal | None = Field(default=None, alias="from")
    upper: Decimal | None = Field(default=None, alias="to")


class _Missing(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = "нет данных"
    woe: Decimal
    points: int


class _Feature(BaseModel):
    model_config = ConfigDict(extra="forbid")

    floor: Decimal | None = None
    cap: Decimal | None = None
    optional: bool = False
    bins: list[_Bin] = Field(min_length=1)
    missing: _Missing


class _Calibration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score: int
    odds: Decimal = Field(gt=0)
    pdo: int = Field(gt=0)


class _Card(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1)
    base: int
    calibration: _Calibration
    features: dict[str, _Feature]


class _ModelSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    min_turnover_months: int = Field(ge=0)
    industry_sections: dict[str, list[int]]
    revenue_mismatch_share: Decimal = Field(gt=0, le=1)
    grades: dict[str, Decimal]
    scorecards: dict[str, _Card]


def load_pd_model(name: str = _DEFAULT_MODEL) -> PdModel:
    return load_pd_model_file(_CONFIG_DIR / f"{name}.yaml")


def load_pd_model_file(path: Path) -> PdModel:
    try:
        raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ScorecardConfigError(f"Не удалось прочитать модель {path}: {exc}") from exc
    try:
        schema = _ModelSchema.model_validate(raw)
    except ValidationError as exc:
        raise ScorecardConfigError(f"Модель {path} не прошла схему: {exc}") from exc
    _check_model(schema, path)
    return PdModel(
        PdModelConfig(
            version=schema.version,
            min_turnover_months=schema.min_turnover_months,
            scorecards={
                segment: _card(card)  # type: ignore[misc]
                for segment, card in schema.scorecards.items()
            },
            grades=tuple((grade, schema.grades[grade]) for grade in _PD_GRADES),
            industry_low=frozenset(schema.industry_sections.get("low", [])),
            industry_high=frozenset(schema.industry_sections.get("high", [])),
            revenue_mismatch_share=schema.revenue_mismatch_share,
        )
    )


@lru_cache(maxsize=4)
def default_model() -> PdModel:
    """Действующая модель, загружается один раз на процесс."""
    return load_pd_model()


def _card(card: _Card) -> ScorecardSpec:
    return ScorecardSpec(
        code=card.code,
        base=card.base,
        calibration=Calibration(
            card.calibration.score, card.calibration.odds, card.calibration.pdo
        ),
        features=tuple(
            FeatureSpec(
                code=code,
                bins=tuple(
                    BinSpec(b.label, b.woe, b.points, b.category, b.lower, b.upper)
                    for b in feature.bins
                ),
                missing=BinSpec(feature.missing.label, feature.missing.woe, feature.missing.points),
                floor=feature.floor,
                cap=feature.cap,
                optional=feature.optional,
            )
            for code, feature in card.features.items()
        ),
    )


def _check_model(schema: _ModelSchema, path: Path) -> None:
    if set(schema.scorecards) != _SEGMENTS:
        raise ScorecardConfigError(f"Модель {path}: нужны скоркарты сегментов {sorted(_SEGMENTS)}")
    if set(schema.grades) != set(_PD_GRADES):
        raise ScorecardConfigError(f"Модель {path}: нужны границы PD грейдов {list(_PD_GRADES)}")
    bounds = [schema.grades[grade] for grade in _PD_GRADES]
    if any(low >= high for low, high in zip(bounds, bounds[1:], strict=False)) or not (
        0 < bounds[0] and bounds[-1] < 1
    ):
        raise ScorecardConfigError(f"Модель {path}: границы PD грейдов должны расти в (0; 1)")
    for section in ("low", "high"):
        if section not in schema.industry_sections:
            raise ScorecardConfigError(f"Модель {path}: нет секции industry_sections.{section}")
    for segment, card in schema.scorecards.items():
        where = f"Модель {path}, скоркарта {segment}"
        unknown = set(card.features) - set(FEATURES)
        if unknown:
            raise ScorecardConfigError(f"{where}: неизвестные признаки {sorted(unknown)}")
        missing = _REQUIRED_FEATURES - set(card.features)
        if missing:
            raise ScorecardConfigError(f"{where}: нет признаков {sorted(missing)}")
        for code, feature in card.features.items():
            _check_bins(f"{where}, признак {code!r}", code, feature)


def _check_bins(where: str, code: str, feature: _Feature) -> None:
    categories = {b.category for b in feature.bins if b.category is not None}
    lacking = _CATEGORIES.get(code, frozenset()) - categories
    if lacking:
        raise ScorecardConfigError(f"{where}: нет бинов категорий {sorted(lacking)}")
    numeric = sorted(
        (b for b in feature.bins if b.category is None),
        key=lambda b: b.lower if b.lower is not None else Decimal("-Infinity"),
    )
    if code not in _NUMERIC:
        if numeric:
            raise ScorecardConfigError(f"{where}: у категориального признака интервальные бины")
        return
    if not numeric:
        raise ScorecardConfigError(f"{where}: нет интервальных бинов")
    first, last = numeric[0], numeric[-1]
    if first.lower is not None and (feature.floor is None or first.lower > feature.floor):
        raise ScorecardConfigError(f"{where}: бины не покрывают значения ниже {first.lower}")
    if last.upper is not None and (feature.cap is None or last.upper <= feature.cap):
        raise ScorecardConfigError(f"{where}: бины не покрывают значения от {last.upper}")
    for left, right in zip(numeric, numeric[1:], strict=False):
        if left.upper is None or left.upper != right.lower:
            raise ScorecardConfigError(
                f"{where}: дырка или перекрытие бинов между {left.label!r} и {right.label!r}"
            )
