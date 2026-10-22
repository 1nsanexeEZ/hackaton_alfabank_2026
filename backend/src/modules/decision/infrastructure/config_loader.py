"""Загрузка кредитной политики и текстов для клиента из YAML с валидацией Pydantic.

Политика — данные, а не код: пороги, коэффициенты и тексты живут в `config/policy_v1.yaml` и
`config/explanations_ru.yaml`. Оба файла проверяются при старте; невалидный YAML (нет грейда,
кода причины, текста или неизвестная подстановка) → `PolicyConfigError`, и приложение не
стартует — лучше сразу, чем молча решить не так.
"""

from __future__ import annotations

import string
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src.modules.decision.domain.explanations import (
    CONDITION_KEYS,
    NOTE_KEYS,
    PLACEHOLDERS,
    ExplanationCatalog,
    ReasonText,
)
from src.modules.decision.domain.model import ReasonCode
from src.modules.decision.domain.policy import CreditPolicy, PolicyConfig

_CONFIG_DIR = Path(__file__).resolve().parent / "config"
_DEFAULT_POLICY = "policy_v1"
_DEFAULT_EXPLANATIONS = "explanations_ru"

_GRADES = frozenset({"A", "B", "C", "D"})
_OUTCOMES = frozenset({"APPROVE", "COUNTER_OFFER", "REQUEST_INFO", "MANUAL_REVIEW", "REJECT"})


class PolicyConfigError(Exception):
    """Политика или тексты в YAML не прошли валидацию — приложение не должно стартовать."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _StopFactors(_Strict):
    registry_statuses: dict[str, ReasonCode]
    overdue_days: int = Field(ge=0)
    grades: list[str]


class _InfoRequest(_Strict):
    revenue_document: str


class _Limits(_Strict):
    revenue_multiplier: dict[str, Decimal]
    ltv: dict[str, Decimal]
    payment_share: Decimal = Field(gt=0, le=1)
    assumed_expense_ratio: Decimal = Field(ge=0, le=1)
    amount_step: Decimal = Field(gt=0)


class _Pricing(_Strict):
    grade_premium: dict[str, Decimal]
    collateral_discount: Decimal = Field(ge=0)
    collateral_min_coverage: Decimal = Field(gt=0)


class _Routing(_Strict):
    grades: list[str]
    flags: dict[str, ReasonCode]


class _Alternatives(_Strict):
    cash_gap_products: list[str]
    secured_product: str
    small_amount_product: str


class _Offer(_Strict):
    valid_days: int = Field(gt=0)


class _PolicySchema(_Strict):
    version: str
    key_rate_reference: Decimal = Field(ge=0)
    stop_factors: _StopFactors
    info_request: _InfoRequest
    limits: _Limits
    pricing: _Pricing
    routing: _Routing
    alternatives: _Alternatives
    offer: _Offer


class _ReasonText(_Strict):
    text: str = Field(min_length=1)
    hint: str | None = None


class _ExplanationsSchema(_Strict):
    version: str
    outcomes: dict[str, str]
    reasons: dict[ReasonCode, _ReasonText]
    notes: dict[str, str]
    conditions: dict[str, str]
    products: dict[str, str]
    collateral_types: dict[str, str]


def load_policy(
    policy: str = _DEFAULT_POLICY, explanations: str = _DEFAULT_EXPLANATIONS
) -> CreditPolicy:
    return load_policy_files(_CONFIG_DIR / f"{policy}.yaml", _CONFIG_DIR / f"{explanations}.yaml")


def load_policy_files(policy_path: Path, explanations_path: Path) -> CreditPolicy:
    policy = _validate(_PolicySchema, policy_path)
    texts = _validate(_ExplanationsSchema, explanations_path)
    _check_policy(policy, policy_path)
    _check_explanations(texts, explanations_path)
    _check_cross(policy, texts, explanations_path)
    return CreditPolicy(_policy_config(policy), _catalog(texts))


@lru_cache(maxsize=4)
def default_policy() -> CreditPolicy:
    """Политика по умолчанию, загружается один раз на процесс."""
    return load_policy()


def _validate[S: BaseModel](schema: type[S], path: Path) -> S:
    try:
        raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise PolicyConfigError(f"Не удалось прочитать {path}: {exc}") from exc
    try:
        return schema.model_validate(raw)
    except ValidationError as exc:
        raise PolicyConfigError(f"{path} не прошёл схему: {exc}") from exc


def _check_policy(schema: _PolicySchema, path: Path) -> None:
    for name, mapping in (
        ("limits.revenue_multiplier", schema.limits.revenue_multiplier),
        ("pricing.grade_premium", schema.pricing.grade_premium),
    ):
        missing = _GRADES - mapping.keys()
        if missing:
            raise PolicyConfigError(f"{path}: в {name} нет грейдов {sorted(missing)}")
    if not schema.alternatives.cash_gap_products:
        raise PolicyConfigError(f"{path}: пустой alternatives.cash_gap_products")


def _check_explanations(schema: _ExplanationsSchema, path: Path) -> None:
    for title, required, present in (
        ("outcomes", _OUTCOMES, schema.outcomes.keys()),
        ("reasons", frozenset(ReasonCode), schema.reasons.keys()),
        ("notes", NOTE_KEYS, schema.notes.keys()),
        ("conditions", CONDITION_KEYS, schema.conditions.keys()),
    ):
        missing = required - present
        if missing:
            raise PolicyConfigError(f"{path}: в {title} нет {sorted(missing)}")
    templates = [
        *schema.outcomes.values(),
        *schema.notes.values(),
        *schema.conditions.values(),
        *(r.text for r in schema.reasons.values()),
        *(r.hint for r in schema.reasons.values() if r.hint),
    ]
    for template in templates:
        unknown = {
            field for _, field, _, _ in string.Formatter().parse(template) if field
        } - PLACEHOLDERS
        if unknown:
            raise PolicyConfigError(f"{path}: неизвестные подстановки {sorted(unknown)}")


def _check_cross(policy: _PolicySchema, texts: _ExplanationsSchema, path: Path) -> None:
    alternatives = policy.alternatives
    codes = {
        *alternatives.cash_gap_products,
        alternatives.secured_product,
        alternatives.small_amount_product,
    }
    missing = codes - texts.products.keys()
    if missing:
        raise PolicyConfigError(f"{path}: нет названий продуктов-альтернатив {sorted(missing)}")
    missing_collateral = policy.limits.ltv.keys() - texts.collateral_types.keys()
    if missing_collateral:
        raise PolicyConfigError(f"{path}: нет названий залогов {sorted(missing_collateral)}")


def _policy_config(schema: _PolicySchema) -> PolicyConfig:
    return PolicyConfig(
        version=schema.version,
        key_rate_reference=schema.key_rate_reference,
        stop_registry_statuses=dict(schema.stop_factors.registry_statuses),
        stop_overdue_days=schema.stop_factors.overdue_days,
        stop_grades=frozenset(schema.stop_factors.grades),
        revenue_document=schema.info_request.revenue_document,
        revenue_multiplier=dict(schema.limits.revenue_multiplier),
        ltv=dict(schema.limits.ltv),
        payment_share=schema.limits.payment_share,
        assumed_expense_ratio=schema.limits.assumed_expense_ratio,
        amount_step=schema.limits.amount_step,
        grade_premium=dict(schema.pricing.grade_premium),
        collateral_discount=schema.pricing.collateral_discount,
        collateral_min_coverage=schema.pricing.collateral_min_coverage,
        manual_review_grades=frozenset(schema.routing.grades),
        routing_flags=dict(schema.routing.flags),
        cash_gap_products=tuple(schema.alternatives.cash_gap_products),
        secured_product=schema.alternatives.secured_product,
        small_amount_product=schema.alternatives.small_amount_product,
        offer_valid_days=schema.offer.valid_days,
    )


def _catalog(schema: _ExplanationsSchema) -> ExplanationCatalog:
    return ExplanationCatalog(
        version=schema.version,
        outcomes=dict(schema.outcomes),
        reasons={code: ReasonText(r.text, r.hint) for code, r in schema.reasons.items()},
        notes=dict(schema.notes),
        conditions=dict(schema.conditions),
        products=dict(schema.products),
        collateral_types=dict(schema.collateral_types),
    )
