"""Синтетическая популяция заявок МСБ для обучения ML-челленджера.

Реальных исходов (дефолт / не дефолт) у нас нет, поэтому генерируем популяцию, где дефолт
задаётся **отдельным «истинным» процессом**, а не нашей скоркартой: иначе модель просто
выучила бы наши же правила. Истинный риск зависит от скрытых величин, которые модель напрямую
не видит (реальная маржа денежного потока, его волатильность, завышение выручки в анкете), и
имеет другой вид, чем баллы скоркарты: покрытие платежа денежным потоком, нелинейность,
взаимодействие «молодой бизнес × нет кредитной истории», случайный шум.

Каждая заявка — тот же `ScoringInput`, что видит прод, так что признаки для обучения считает
та же функция, что и в инференсе. Генерация детерминирована (seed).

Это честно синтетические данные: в проде модель переобучается на истории банка, интерфейс
и формат коэффициентов остаются теми же.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import numpy as np

from src.modules.scoring.domain.model import (
    BureauInput,
    CashflowInput,
    CollateralInput,
    CompanyInput,
    RequestInput,
    ScoringInput,
    TaxInput,
)
from src.modules.scoring.domain.scorecard import estimated_payment

_AS_OF = date(2026, 10, 1)
_SECTIONS = {
    "low": (62, 63, 69, 70, 71, 72, 73, 74, 86),
    "mid": (10, 25, 33, 45, 46, 47, 49, 52, 68, 77, 82, 85, 96),
    "high": (41, 42, 43, 55, 56, 79),
}
_INDUSTRY_WEIGHTS = {"low": 0.25, "mid": 0.55, "high": 0.20}


@dataclass(frozen=True)
class Macro:
    """Условия кредитования когорты: сдвиг роста выручки, ставок и общий стресс."""

    name: str
    growth_shift: float = 0.0
    rate_shift: float = 0.0
    stress: float = 0.0


@dataclass(frozen=True)
class Assumptions:
    """Наши допущения о «правде» — их варьирует проверка устойчивости (`ml.validate`)."""

    fraud_share: float = 0.12  # доля заявок с завышенной выручкой
    margin_mean: float = 0.18  # средний операционный поток, доля выручки
    noise: float = 0.5  # случайная составляющая риска (то, чего не видит никто)
    coverage_weight: float = 1.6  # сила влияния непокрытых платежей на дефолт
    # Общий уровень риска (свободный член истинного процесса). Подобран так, чтобы доля дефолтов
    # совпадала со средним PD экспертной `pd_model_v2` на этой же популяции: уровень дефолтов
    # синтетики — наше допущение, а калибровку портфеля банк уже задал в PD-модели. Так PD двух
    # моделей стоят на одной шкале и грейды A–J сравнимы.
    base_logit: float = -5.0


BASELINE = Assumptions()
DEVELOPMENT = Macro("development")
# Когорта «вне времени»: рост выручки ниже, ставки выше, рисков больше — проверка стабильности.
OUT_OF_TIME = Macro("out_of_time", growth_shift=-0.08, rate_shift=4.0, stress=0.25)


@dataclass(frozen=True)
class Applicant:
    inp: ScoringInput
    defaulted: int  # дефолт в течение 12 месяцев
    true_pd: float  # вероятность из истинного процесса (для отчёта, модели не видна)


def generate(
    n: int, seed: int, macro: Macro = DEVELOPMENT, assumptions: Assumptions = BASELINE
) -> list[Applicant]:
    rng = np.random.default_rng(seed)
    return [_applicant(rng, macro, assumptions) for _ in range(n)]


def _applicant(rng: np.random.Generator, macro: Macro, a: Assumptions) -> Applicant:
    is_ie = rng.random() < 0.30
    age = int(np.clip(math.exp(rng.normal(math.log(40), 0.9)), 3, 300))
    revenue = float(np.clip(math.exp(rng.normal(math.log(6e6 if is_ie else 25e6), 0.9)), 1e6, 5e8))
    revenue = round(revenue, -3)

    # Скрытая экономика бизнеса — модель её напрямую не видит.
    growth = float(np.clip(rng.normal(0.06 + macro.growth_shift, 0.20), -0.7, 1.5))
    overstate = 0.0 if rng.random() < 1 - a.fraud_share else float(rng.uniform(0.15, 0.70))
    true_revenue = revenue * (1 - overstate)
    industry = rng.choice(list(_INDUSTRY_WEIGHTS), p=list(_INDUSTRY_WEIGHTS.values()))
    # Операционный денежный поток для обслуживания долга, доля выручки (≈ EBITDA-маржа).
    margin = float(rng.normal(a.margin_mean, 0.08)) - (0.05 if industry == "high" else 0.0)
    volatility = float(rng.uniform(0.1, 1.0))

    previous = None
    if age >= 24:
        previous = round(revenue / (1 + growth + float(rng.normal(0, 0.03))), -3)
    reported = None
    if rng.random() >= 0.03:
        reported = round(true_revenue * (1 + float(rng.normal(0, 0.03))), -3)
    arrears = 0.0
    if rng.random() < 0.06 + (0.10 if margin < 0.08 else 0.0):
        arrears = round(float(rng.uniform(10_000, 500_000)), -2)
    section = int(rng.choice(_SECTIONS[industry]))
    okved = f"{section}.{int(rng.integers(10, 99))}"
    roll = rng.random()
    verification = "mismatch" if roll < 0.06 else "unverified" if roll < 0.10 else "verified"

    # Кредитная история.
    has_debt = rng.random() < 0.65
    current_payments = true_revenue / 12 * float(rng.uniform(0.02, 0.35)) if has_debt else 0.0
    available = rng.random() < 0.96
    has_history = has_debt or (age >= 12 and rng.random() < 0.5)
    distress = _sigmoid(-2.2 + 6 * (0.12 - margin) + 0.8 * volatility + macro.stress)
    overdue = 0
    if has_history and rng.random() < distress:
        overdue = int(rng.choice([15, 60, 120], p=[0.6, 0.25, 0.15]))
    inquiries = int(rng.poisson(0.8 + (2.5 if margin < 0.10 else 0.0) + 2 * macro.stress))

    # Заявка.
    amount = revenue * math.exp(rng.normal(math.log(0.15), 0.7))
    amount = float(np.clip(round(amount, -4), 300_000, min(50_000_000, 2 * revenue)))
    term = int(rng.choice([12, 24, 36, 48, 60]))
    rate = 23.5 + macro.rate_shift
    collateral = amount * float(rng.uniform(0.5, 2.5)) if rng.random() < 0.15 else None
    new_payment = float(estimated_payment(Decimal(str(amount)), term, Decimal(str(rate))))

    # Выписка: разрыв виден, если поток не покрывает платежи с учётом волатильности.
    free_cash = true_revenue / 12 * margin
    payments = current_payments + new_payment
    statement = rng.random() < 0.45
    gap = free_cash * (1 - 0.9 * volatility) < payments

    # Истинный процесс дефолта.
    coverage = free_cash / payments if payments > 0 else 5.0
    z = (
        a.base_logit
        + macro.stress
        + a.coverage_weight * min(2.0, max(0.0, 1.3 - coverage))
        + {0: 0.0, 15: 0.4, 60: 1.0, 120: 1.8}[overdue]
        + (0.6 if age < 12 and not has_history else 0.0)
        + 1.2 * max(0.0, -growth)
        + (0.5 if arrears > 0 else 0.0)
        + 1.5 * overstate
        + 0.12 * inquiries
        + 0.5 * volatility
        - 0.35 * math.log(1 + age / 12)
        + {"low": -0.25, "mid": 0.0, "high": 0.35}[industry]
        - (0.5 if collateral is not None and collateral >= amount else 0.0)
        + (0.35 if verification == "mismatch" else 0.0)
        + float(rng.normal(0, a.noise))
    )
    true_pd = _sigmoid(z)
    defaulted = int(rng.random() < true_pd)

    inp = ScoringInput(
        request=RequestInput(
            amount=_rub(amount),
            term_months=term,
            product_code="UNSECURED",
            facility="term_loan",
            rate_base=Decimal(str(rate)),
        ),
        company=CompanyInput(
            legal_form="IE" if is_ie else "LLC",
            business_age_months=age,
            okved_main=okved,
            verification_status=verification,
            registry_status="active",
            declared_revenue=_rub(revenue),
            declared_revenue_previous=_rub(previous) if previous is not None else None,
            monthly_debt_payments_declared=None,
        ),
        tax=TaxInput(
            tax_arrears=_rub(arrears) if reported is not None else None,
            reported_revenue=_rub(reported) if reported is not None else None,
        ),
        bureau=BureauInput(
            available=available,
            has_history=has_history,
            max_overdue_days_12m=overdue if available and has_history else None,
            inquiries_last_30d=inquiries if available else None,
            total_monthly_payments=_rub(current_payments) if available else Decimal(0),
        ),
        collateral=CollateralInput(_rub(collateral) if collateral is not None else None),
        cashflow=CashflowInput(
            present=statement,
            gap_detected=gap if statement else None,
            gap_month=None,
            gap_amount=None,
            revenue_confirmed=(overstate < 0.30) if statement else None,
        ),
        mass_address=False,
        sources_failed=() if available else ("bki",),
        as_of=_AS_OF,
    )
    return Applicant(inp=inp, defaulted=defaulted, true_pd=true_pd)


def _sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x))


def _rub(value: float) -> Decimal:
    return Decimal(str(round(value, 2))).quantize(Decimal("0.01"))
