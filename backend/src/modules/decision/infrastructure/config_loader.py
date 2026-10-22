"""Загрузка кредитной политики и текстов для клиента из YAML с валидацией Pydantic.

Политика — данные, а не код: пороги, коэффициенты и тексты живут в `config/policy_v<N>.yaml` и
`config/explanations_ru.yaml`. Действует последняя версия (`policy_v3`); прежние лежат рядом для
golden-тестов и отката. Оба файла проверяются при старте; невалидный YAML (нет грейда,
кода причины, текста, грейд вне матрицы или неизвестная подстановка) → `PolicyConfigError`, и
приложение не стартует — лучше сразу, чем молча решить не так.
"""

from __future__ import annotations

import re
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
from src.modules.decision.domain.model import LEGACY_SCALE, PD_SCALE, Grade, ReasonCode
from src.modules.decision.domain.policy import (
    CreditPolicy,
    MatrixBand,
    PolicyConfig,
    RateComponents,
)

_CONFIG_DIR = Path(__file__).resolve().parent / "config"
_DEFAULT_POLICY = "policy_v3"
_DEFAULT_EXPLANATIONS = "explanations_ru"

_SCALES: tuple[tuple[Grade, ...], ...] = (LEGACY_SCALE, PD_SCALE)
_OKVED_CLASS = re.compile(r"^\d{2}$")
_OUTCOMES = frozenset({"APPROVE", "COUNTER_OFFER", "REQUEST_INFO", "MANUAL_REVIEW", "REJECT"})


class PolicyConfigError(Exception):
    """Политика или тексты в YAML не прошли валидацию — приложение не должно стартовать."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _StopFactors(_Strict):
    registry_statuses: dict[str, ReasonCode]
    overdue_days: int = Field(ge=0)
    grades: list[str]
    # policy_v2: нет ключа — правило выключено.
    current_overdue_days: int | None = Field(default=None, ge=1)
    account_blocks: bool = False
    tax_arrears_above: Decimal | None = Field(default=None, ge=0)
    bankruptcy_messages: bool = False
    enforcement_revenue_share: Decimal | None = Field(default=None, gt=0, le=1)
    lawsuits_revenue_share: Decimal | None = Field(default=None, gt=0, le=1)
    negative_equity: bool = False
    mass_address: bool = False
    okved_classes: list[str] = Field(default_factory=list)


class _InfoRequest(_Strict):
    revenue_document: str


class _Limits(_Strict):
    revenue_multiplier: dict[str, Decimal]
    ltv: dict[str, Decimal]
    payment_share: Decimal = Field(gt=0, le=1)
    assumed_expense_ratio: Decimal = Field(ge=0, le=1)
    amount_step: Decimal = Field(gt=0)
    # policy_v3
    turnover_multiplier: Decimal | None = Field(default=None, gt=0)
    grade_max_amount: dict[str, Decimal] = Field(default_factory=dict)
    group_exposure_max: Decimal | None = Field(default=None, ge=0)


class _Components(_Strict):
    funding_spread: Decimal
    lgd_unsecured: Decimal = Field(ge=0, le=1)
    lgd_secured: Decimal = Field(ge=0, le=1)
    capital: Decimal = Field(ge=0)
    margin: Decimal = Field(ge=0)
    pd_if_unknown: Decimal = Field(gt=0, lt=1)


class _Pricing(_Strict):
    # policy_v1/v2 — надбавка за грейд и скидка за залог; policy_v3 — компоненты ставки.
    grade_premium: dict[str, Decimal] = Field(default_factory=dict)
    collateral_discount: Decimal = Field(default=Decimal(0), ge=0)
    collateral_min_coverage: Decimal = Field(gt=0)
    components: _Components | None = None


class _Routing(_Strict):
    grades: list[str]
    flags: dict[str, ReasonCode]
    tax_arrears: bool = False  # policy_v2


class _TurnoverSpike(_Strict):
    recent_months: int = Field(ge=1)
    ratio: Decimal = Field(gt=1)


class _SoftTriggers(_Strict):
    tax_arrears: bool = False
    head_change_months: int | None = Field(default=None, ge=1)
    turnover_spike: _TurnoverSpike | None = None


class _Band(_Strict):
    label: str = Field(min_length=1)
    grades: list[str] = Field(min_length=1)
    approve_up_to: Decimal = Field(ge=0)
    manual_up_to: Decimal | None = Field(default=None, ge=0)


class _Guarantee(_Strict):
    grades: list[str] = Field(default_factory=list)
    amount_above: Decimal | None = Field(default=None, gt=0)


class _Strategy(_Strict):
    """policy_v3: мягкие триггеры, матрица грейд × сумма, поручительство."""

    soft_triggers: _SoftTriggers = Field(default_factory=_SoftTriggers)
    risk_matrix: list[_Band] = Field(default_factory=list)
    guarantee: _Guarantee = Field(default_factory=_Guarantee)


class _Alternatives(_Strict):
    cash_gap_products: list[str]
    secured_product: str
    small_amount_product: str


class _Offer(_Strict):
    valid_days: int = Field(gt=0)


class _PolicySchema(_Strict):
    version: str
    key_rate_reference: Decimal = Field(ge=0)
    # Шкала грейдов; нет ключа — A–E scorecard_v1 (policy_v1, policy_v2).
    grades: list[str] = Field(default_factory=lambda: list(LEGACY_SCALE))
    stop_factors: _StopFactors
    info_request: _InfoRequest
    limits: _Limits
    pricing: _Pricing
    routing: _Routing
    strategy: _Strategy = Field(default_factory=_Strategy)
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
    scale = tuple(schema.grades)
    if scale not in _SCALES:
        raise PolicyConfigError(
            f"{path}: шкала грейдов — {list(LEGACY_SCALE)} или {list(PD_SCALE)}"
        )
    # Грейды, по которым решение не отказ по стоп-фактору, — для них нужны коэффициенты.
    graded = frozenset(scale) - frozenset(schema.stop_factors.grades)
    mappings = [
        ("limits.revenue_multiplier", schema.limits.revenue_multiplier),
        ("pricing.grade_premium", schema.pricing.grade_premium),
    ]
    if schema.pricing.components is not None:
        mappings.pop()
    if schema.limits.grade_max_amount:
        mappings.append(("limits.grade_max_amount", schema.limits.grade_max_amount))
    for name, mapping in mappings:
        missing = graded - mapping.keys()
        if missing:
            raise PolicyConfigError(f"{path}: в {name} нет грейдов {sorted(missing)}")
    _check_strategy(schema, scale, path)
    if not schema.alternatives.cash_gap_products:
        raise PolicyConfigError(f"{path}: пустой alternatives.cash_gap_products")
    bad_okved = [c for c in schema.stop_factors.okved_classes if not _OKVED_CLASS.match(c)]
    if bad_okved:
        raise PolicyConfigError(
            f"{path}: в stop_factors.okved_classes нужны двузначные классы: {bad_okved}"
        )


def _check_strategy(schema: _PolicySchema, scale: tuple[str, ...], path: Path) -> None:
    strategy = schema.strategy
    seen: list[str] = [g for band in strategy.risk_matrix for g in band.grades]
    if strategy.risk_matrix and (len(seen) != len(set(seen)) or set(seen) != set(scale)):
        raise PolicyConfigError(
            f"{path}: strategy.risk_matrix должна покрыть каждый грейд {list(scale)} ровно раз"
        )
    for band in strategy.risk_matrix:
        if band.manual_up_to is not None and band.manual_up_to < band.approve_up_to:
            raise PolicyConfigError(f"{path}: в корзине {band.label} manual_up_to < approve_up_to")
    unknown = set(strategy.guarantee.grades) - set(scale)
    if unknown:
        raise PolicyConfigError(f"{path}: strategy.guarantee.grades вне шкалы: {sorted(unknown)}")


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
    stops = schema.stop_factors
    strategy = schema.strategy
    triggers = strategy.soft_triggers
    spike = triggers.turnover_spike
    components = schema.pricing.components
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
        stop_current_overdue_days=stops.current_overdue_days,
        stop_account_blocks=stops.account_blocks,
        stop_tax_arrears_above=stops.tax_arrears_above,
        stop_bankruptcy_messages=stops.bankruptcy_messages,
        stop_enforcement_share=stops.enforcement_revenue_share,
        stop_lawsuits_share=stops.lawsuits_revenue_share,
        stop_negative_equity=stops.negative_equity,
        stop_mass_address=stops.mass_address,
        stop_okved_classes=frozenset(stops.okved_classes),
        route_tax_arrears=schema.routing.tax_arrears,
        grade_scale=tuple(schema.grades),  # type: ignore[arg-type]
        risk_matrix=tuple(
            MatrixBand(b.label, frozenset(b.grades), b.approve_up_to, b.manual_up_to)
            for b in strategy.risk_matrix
        ),
        trigger_tax_arrears=triggers.tax_arrears,
        trigger_head_change_months=triggers.head_change_months,
        trigger_turnover_months=spike.recent_months if spike is not None else None,
        trigger_turnover_ratio=spike.ratio if spike is not None else None,
        turnover_multiplier=schema.limits.turnover_multiplier,
        grade_max_amount=dict(schema.limits.grade_max_amount),
        group_exposure_max=schema.limits.group_exposure_max,
        rate_components=RateComponents(
            funding_spread=components.funding_spread,
            lgd_unsecured=components.lgd_unsecured,
            lgd_secured=components.lgd_secured,
            capital=components.capital,
            margin=components.margin,
            pd_if_unknown=components.pd_if_unknown,
        )
        if components is not None
        else None,
        guarantee_grades=frozenset(strategy.guarantee.grades),
        guarantee_amount_above=strategy.guarantee.amount_above,
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
