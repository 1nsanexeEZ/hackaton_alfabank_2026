"""ML-модель вероятности дефолта: логистическая регрессия на WoE-признаках, обученная на данных.

Работает рядом с PD-моделью (`pd_model.py`) — обе считаются на каждой заявке, и решение
(`policy_v5`) смотрит на обе. Разница — откуда взялись числа: в PD-модели бины, WoE и баллы
задал эксперт, здесь веса подобраны обучением (`backend/ml/train.py`) на данных с известным
исходом. В прод приходят только корзины и коэффициенты (YAML), поэтому инференс — чистый
Python на `Decimal`, воспроизводимый бит в бит.

Грейд — на той же шкале A–J и по тем же границам PD, что у PD-модели: админ сравнивает
модели напрямую. Коды причин — топ-3 признака по баллам, недобранным до лучшей корзины, как у
PD-модели.

Признаки считает `ml_features` — одна функция и для обучения, и для прода: обучение и
инференс не могут разъехаться. Справочник отраслей (секции ОКВЭД низкого и высокого риска) —
в YAML модели: на нём посчитаны WoE, и правка конфига PD-модели его не меняет.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, localcontext

from src.modules.scoring.domain.model import Direction, Factor, Grade, MlScore, ScoringInput
from src.modules.scoring.domain.scorecard import estimated_payment, okved_section

FeatureValue = Decimal | str | None

_PD_STEP = Decimal("0.0001")
_RATIO_STEP = Decimal("0.0001")
_REASON_CODES = 3
_LAST_GRADE: Grade = "J"


@dataclass(frozen=True, slots=True)
class NumericBin:
    upper: Decimal | None  # верхняя граница не включительно; None — до бесконечности
    woe: Decimal
    label: str


@dataclass(frozen=True, slots=True)
class FeatureSpec:
    name: str
    title: str  # как показать админу
    kind: str  # numeric | category
    coef: Decimal
    missing_woe: Decimal
    bins: tuple[NumericBin, ...] = ()
    categories: tuple[tuple[str, Decimal], ...] = ()

    def woes(self) -> tuple[Decimal, ...]:
        values = [b.woe for b in self.bins] + [w for _, w in self.categories]
        return (*values, self.missing_woe)


@dataclass(frozen=True, slots=True)
class IndustrySections:
    """Секции ОКВЭД (две первые цифры) низкого и высокого риска; остальные — средний."""

    low: frozenset[int]
    high: frozenset[int]


@dataclass(frozen=True, slots=True)
class MlConfig:
    version: str
    intercept: Decimal
    features: tuple[FeatureSpec, ...]
    base_score: Decimal  # баллы при шансах base_odds «хороший : плохой»
    base_odds: Decimal
    pdo: Decimal  # на сколько баллов растёт скор при удвоении шансов
    grade_bands: tuple[tuple[Grade, Decimal], ...]  # грейд и верхняя граница PD (не включительно)
    industry: IndustrySections


def ml_features(inp: ScoringInput, industry: IndustrySections) -> dict[str, FeatureValue]:
    """Сырые признаки модели из входа скоринга; None — данных нет."""
    company, bureau, request = inp.company, inp.bureau, inp.request
    revenue = company.declared_revenue or inp.tax.reported_revenue
    revenue_ok = revenue is not None and revenue > 0

    growth: FeatureValue = None
    previous = company.declared_revenue_previous
    if company.declared_revenue is not None and previous is not None and previous > 0:
        growth = _ratio(company.declared_revenue / previous - 1)

    debt_service: FeatureValue = None
    amount_to_revenue: FeatureValue = None
    if revenue_ok:
        assert revenue is not None
        current = (
            bureau.total_monthly_payments
            if bureau.available
            else company.monthly_debt_payments_declared or Decimal(0)
        )
        new_payment = estimated_payment(request.amount, request.term_months, request.rate_base)
        debt_service = _ratio((current + new_payment) / (revenue / 12))
        amount_to_revenue = _ratio(request.amount / revenue)

    revenue_gap: FeatureValue = None
    declared, reported = company.declared_revenue, inp.tax.reported_revenue
    if declared is not None and declared > 0 and reported is not None:
        revenue_gap = _ratio(abs(declared - reported) / declared)

    if not bureau.available:
        overdue: FeatureValue = "unavailable"
    elif not bureau.has_history:
        overdue = "no_history"
    else:
        days = bureau.max_overdue_days_12m or 0
        overdue = "0" if days == 0 else "1-30" if days <= 30 else "31-90" if days <= 90 else "90+"

    inquiries: FeatureValue = Decimal(bureau.inquiries_last_30d or 0) if bureau.available else None

    arrears = inp.tax.tax_arrears
    tax_arrears: FeatureValue = None if arrears is None else ("yes" if arrears > 0 else "no")

    cashflow = inp.cashflow
    if not cashflow.present:
        cash_gap: FeatureValue = "no_statement"
    else:
        cash_gap = "gap" if cashflow.gap_detected else "no_gap"
    if cashflow.revenue_confirmed is None:
        confirmed: FeatureValue = "unknown"
    else:
        confirmed = "yes" if cashflow.revenue_confirmed else "no"

    coverage: FeatureValue = None
    if inp.collateral.declared_value is not None and request.amount > 0:
        coverage = _ratio(inp.collateral.declared_value / request.amount)

    return {
        "business_age_months": Decimal(company.business_age_months),
        "revenue_growth": growth,
        "debt_service_ratio": debt_service,
        "amount_to_revenue": amount_to_revenue,
        "revenue_gap": revenue_gap,
        "bureau_overdue": overdue,
        "bureau_inquiries": inquiries,
        "tax_arrears": tax_arrears,
        "verification": company.verification_status,
        "industry_risk": _industry(company.okved_main, industry),
        "cash_gap": cash_gap,
        "revenue_confirmed": confirmed,
        "collateral_coverage": coverage,
    }


class MlModel:
    def __init__(self, config: MlConfig) -> None:
        self._c = config

    @property
    def version(self) -> str:
        return self._c.version

    @property
    def config(self) -> MlConfig:
        return self._c

    def predict(self, inp: ScoringInput) -> MlScore:
        values = ml_features(inp, self._c.industry)
        with localcontext() as ctx:
            ctx.prec = 34
            factor = self._c.pdo / Decimal(2).ln()
            offset = self._c.base_score - factor * self._c.base_odds.ln()
            logit = self._c.intercept
            factors: list[Factor] = []
            losses: list[tuple[int, int, str]] = []
            for order, spec in enumerate(self._c.features):
                value = values[spec.name]
                woe, label = _woe(spec, value)
                term = spec.coef * woe
                logit += term
                points = _points(factor, term)
                best = max(_points(factor, spec.coef * w) for w in spec.woes())
                if best > points:
                    losses.append((points - best, order, spec.name))
                factors.append(
                    Factor(
                        code=spec.name,
                        value=None if value is None else str(value),
                        bin=label,
                        points=points,
                        direction=_direction(points),
                        has_data=value is not None,
                    )
                )
            pd = (1 / (1 + (-logit).exp())).quantize(_PD_STEP, ROUND_HALF_UP)
            score = int((offset - factor * logit).quantize(Decimal(1), ROUND_HALF_UP))
        return MlScore(
            model_version=self._c.version,
            pd_12m=pd,
            score=score,
            grade=self._grade(pd),
            factors=tuple(factors),
            reason_codes=tuple(code for _, _, code in sorted(losses)[:_REASON_CODES]),
        )

    def _grade(self, pd: Decimal) -> Grade:
        for grade, upper in self._c.grade_bands:
            if pd < upper:
                return grade
        return _LAST_GRADE


def _points(factor: Decimal, term: Decimal) -> int:
    return int((-factor * term).quantize(Decimal(1), ROUND_HALF_UP))


def _woe(spec: FeatureSpec, value: FeatureValue) -> tuple[Decimal, str]:
    if value is None:
        return spec.missing_woe, "нет данных"
    if spec.kind == "category":
        for name, woe in spec.categories:
            if name == value:
                return woe, str(value)
        return spec.missing_woe, f"{value} (не встречалось)"
    assert isinstance(value, Decimal)
    for numeric_bin in spec.bins:
        if numeric_bin.upper is None or value < numeric_bin.upper:
            return numeric_bin.woe, numeric_bin.label
    return spec.missing_woe, "вне корзин"


def _industry(okved_main: str, industry: IndustrySections) -> str:
    section = okved_section(okved_main)
    if section in industry.low:
        return "low"
    if section in industry.high:
        return "high"
    return "mid"


def _ratio(value: Decimal) -> Decimal:
    return value.quantize(_RATIO_STEP, ROUND_HALF_UP)


def _direction(points: int) -> Direction:
    if points > 0:
        return "positive"
    if points < 0:
        return "negative"
    return "neutral"
