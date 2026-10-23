"""PD-модель: сегмент → скоркарта → балл → вероятность дефолта на 12 месяцев → грейд A–J.

По шагам «Модели оценки PD» общей схемы:
1. сегмент: ЮЛ и ИП с оборотами в банке от `min_turnover_months` — свои скоркарты, остальные —
   упрощённая (`new_client`). Отдельной даты «клиент банка с» в данных нет: счёт открывается
   при регистрации (кейс, §5 — предприниматель уже клиент банка), поэтому история оборотов
   в банке — возраст бизнеса;
2. признаки на дату заявки — `features.py`, вход и так зафиксирован на момент подачи;
3. пропуск — бин «нет данных», выброс — винзоризация: значение прижимается к границам признака;
4. биннинг: значение → бин → WoE и баллы; балл = база + сумма баллов;
5. калибровка: шансы «хороший : плохой» = odds × 2^((балл − score) / pdo), PD = 1 / (1 + шансы);
6. грейд A–J по диапазонам PD;
7. коды причин — топ-3 признака с наибольшей потерей баллов: сколько не добрал до лучшего бина.

Бины, WoE, баллы, калибровка и границы грейдов — в YAML (`PdModelConfig`), здесь — только
логика. `calculate` — чистая функция входа: без IO и без `now()`, все расчёты в `Decimal`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from src.modules.scoring.domain.features import (
    FeatureValue,
    bank_notes,
    feature_values,
    risk_flags,
)
from src.modules.scoring.domain.model import Direction, Factor, Grade, ScoringInput, Segment
from src.modules.scoring.domain.scorecard import (
    CLIENT_HINTS,
    MAX_CLIENT_HINTS,
    ScorecardOutput,
    without_hint,
)

_SCORE_MIN, _SCORE_MAX = 0, 1000
_PD_STEP = Decimal("0.0001")
_REASON_CODES = 3
_LAST_GRADE: Grade = "J"


@dataclass(frozen=True, slots=True)
class BinSpec:
    """Категория (`category`) или интервал [`lower`; `upper`), граница None — открытая."""

    label: str
    woe: Decimal
    points: int
    category: str | None = None
    lower: Decimal | None = None
    upper: Decimal | None = None

    def matches(self, value: Decimal | str) -> bool:
        if isinstance(value, str):
            return self.category == value
        if self.category is not None:
            return False
        return (self.lower is None or value >= self.lower) and (
            self.upper is None or value < self.upper
        )


@dataclass(frozen=True, slots=True)
class FeatureSpec:
    code: str
    bins: tuple[BinSpec, ...]
    missing: BinSpec  # бин «нет данных»
    # Винзоризация числового признака: значение прижимается к [floor; cap].
    floor: Decimal | None = None
    cap: Decimal | None = None
    # Признак не про эту заявку (залог у беззалогового продукта): нет данных — его нет в карте.
    optional: bool = False

    @property
    def best_points(self) -> int:
        return max(b.points for b in (*self.bins, self.missing))


@dataclass(frozen=True, slots=True)
class Calibration:
    score: int  # опорный балл
    odds: Decimal  # шансы «хороший : плохой» на опорном балле
    pdo: int  # баллов на удвоение шансов

    def pd(self, score: int) -> Decimal:
        odds = self.odds * Decimal(2) ** (Decimal(score - self.score) / Decimal(self.pdo))
        return (1 / (1 + odds)).quantize(_PD_STEP, rounding=ROUND_HALF_UP)


@dataclass(frozen=True, slots=True)
class ScorecardSpec:
    """Скоркарта сегмента со своей калибровкой: балл сравним внутри сегмента, PD — везде."""

    code: str
    base: int
    calibration: Calibration
    features: tuple[FeatureSpec, ...]


@dataclass(frozen=True, slots=True)
class PdModelConfig:
    version: str
    min_turnover_months: int
    scorecards: Mapping[Segment, ScorecardSpec]
    # (грейд, PD строго меньше) по возрастанию; всё, что выше последней границы, — J.
    grades: tuple[tuple[Grade, Decimal], ...]
    industry_low: frozenset[int]
    industry_high: frozenset[int]
    revenue_mismatch_share: Decimal  # расхождение с ФНС больше — флаг revenue_mismatch


class PdModel:
    def __init__(self, config: PdModelConfig) -> None:
        self._c = config

    @property
    def version(self) -> str:
        return self._c.version

    @property
    def config(self) -> PdModelConfig:
        return self._c

    def segment(self, inp: ScoringInput) -> Segment:
        if inp.company.business_age_months < self._c.min_turnover_months:
            return "new_client"
        return "entrepreneur" if inp.company.legal_form == "IE" else "legal_entity"

    def grade(self, pd: Decimal) -> Grade:
        for grade, below in self._c.grades:
            if pd < below:
                return grade
        return _LAST_GRADE

    def calculate(self, inp: ScoringInput) -> ScorecardOutput:
        segment = self.segment(inp)
        card = self._c.scorecards[segment]
        values = feature_values(inp, self._c.industry_low, self._c.industry_high)

        factors: list[Factor] = []
        losses: list[tuple[int, int, str]] = []
        for order, feature in enumerate(card.features):
            value = values[feature.code]
            if value is None and feature.optional:
                continue
            chosen = feature.missing if value is None else _bin(feature, value)
            factors.append(_factor(feature.code, value, chosen, has_data=value is not None))
            loss = feature.best_points - chosen.points
            if loss > 0:
                losses.append((-loss, order, feature.code))

        score = max(_SCORE_MIN, min(_SCORE_MAX, card.base + sum(f.points for f in factors)))
        pd = card.calibration.pd(score)
        return ScorecardOutput(
            score=score,
            grade=self.grade(pd),
            factors=tuple(_keep_top_hints(factors)),
            flags=risk_flags(inp, values, self._c.revenue_mismatch_share),
            data_completeness=_completeness(factors),
            bank_notes=bank_notes(inp),
            segment=segment,
            scorecard=card.code,
            pd_12m=pd,
            reason_codes=tuple(code for _, _, code in sorted(losses)[:_REASON_CODES]),
        )


def _bin(feature: FeatureSpec, value: Decimal | str) -> BinSpec:
    if isinstance(value, Decimal):
        if feature.floor is not None:
            value = max(value, feature.floor)
        if feature.cap is not None:
            value = min(value, feature.cap)
    for candidate in feature.bins:
        if candidate.matches(value):
            return candidate
    # Конфиг проверяется при загрузке: бины покрывают всю ось, категории — все значения.
    raise ValueError(f"no bin of {feature.code!r} for {value!r}")


def _factor(code: str, value: FeatureValue, chosen: BinSpec, *, has_data: bool) -> Factor:
    direction = _direction(chosen.points)
    return Factor(
        code=code,
        value=_shown(value),
        bin=chosen.label,
        points=chosen.points,
        direction=direction,
        client_hint=CLIENT_HINTS.get(code) if direction == "negative" else None,
        has_data=has_data,
    )


def _shown(value: FeatureValue) -> str | None:
    if value is None or isinstance(value, str):
        return value
    if value == value.to_integral_value():
        return str(value.quantize(Decimal(1)))
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _direction(points: int) -> Direction:
    if points > 0:
        return "positive"
    if points < 0:
        return "negative"
    return "neutral"


def _keep_top_hints(factors: list[Factor]) -> list[Factor]:
    """Подсказки клиенту — только у 2–3 самых негативных признаков."""
    ranked = sorted((f for f in factors if f.client_hint is not None), key=lambda f: f.points)
    keep = {id(f) for f in ranked[:MAX_CLIENT_HINTS]}
    return [f if id(f) in keep or f.client_hint is None else without_hint(f) for f in factors]


def _completeness(factors: list[Factor]) -> Decimal:
    if not factors:
        return Decimal("1.000")
    present = sum(1 for f in factors if f.has_data)
    return (Decimal(present) / Decimal(len(factors))).quantize(Decimal("0.001"), ROUND_HALF_UP)
