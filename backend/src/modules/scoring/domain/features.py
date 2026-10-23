"""Признаки PD-модели на дату заявки: значение для бина или None — данных нет.

Число — для интервальных бинов, строка — для категорий: `thin` у бюро без истории,
`verified` / `mismatch` / `other`, `low` / `mid` / `high`, `none` / `any`, `gap` / `no_gap`.
Флаги для decision и пояснения банку считаются здесь же, по тому же входу.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal

from src.modules.scoring.domain.model import RiskFlag, ScoringInput
from src.modules.scoring.domain.scorecard import estimated_payment, okved_section

FeatureValue = Decimal | str | None

FEATURES: tuple[str, ...] = (
    "business_age",
    "revenue_trend",
    "debt_load",
    "bureau_overdue",
    "bureau_inquiries",
    "tax_arrears",
    "industry_risk",
    "amount_to_revenue",
    "revenue_consistency",
    "verification",
    "collateral_coverage",
    "cash_gap",
)

_TWELVE = Decimal(12)


def feature_values(
    inp: ScoringInput, industry_low: frozenset[int], industry_high: frozenset[int]
) -> Mapping[str, FeatureValue]:
    company, bureau, cashflow = inp.company, inp.bureau, inp.cashflow
    revenue = company.declared_revenue or inp.tax.reported_revenue
    return {
        "business_age": Decimal(company.business_age_months),
        "revenue_trend": _growth(company.declared_revenue, company.declared_revenue_previous),
        "debt_load": _debt_load(inp, revenue),
        "bureau_overdue": (
            None
            if not bureau.available
            else Decimal(bureau.max_overdue_days_12m or 0)
            if bureau.has_history
            else "thin"
        ),
        "bureau_inquiries": (Decimal(bureau.inquiries_last_30d or 0) if bureau.available else None),
        "tax_arrears": (
            None if inp.tax.tax_arrears is None else "any" if inp.tax.tax_arrears > 0 else "none"
        ),
        "industry_risk": _industry(company.okved_main, industry_low, industry_high),
        "amount_to_revenue": (
            inp.request.amount / revenue if revenue is not None and revenue > 0 else None
        ),
        "revenue_consistency": _revenue_gap(inp),
        "verification": (
            company.verification_status
            if company.verification_status in ("verified", "mismatch")
            else "other"
        ),
        "collateral_coverage": (
            inp.collateral.declared_value / inp.request.amount
            if inp.collateral.declared_value is not None and inp.request.amount > 0
            else None
        ),
        "cash_gap": (
            None if not cashflow.present else "gap" if cashflow.gap_detected else "no_gap"
        ),
    }


def risk_flags(
    inp: ScoringInput, values: Mapping[str, FeatureValue], revenue_mismatch_share: Decimal
) -> tuple[RiskFlag, ...]:
    """Те же сигналы, что ставит scorecard_v1: по ним decision маршрутизирует и просит выписку."""
    flags: list[RiskFlag] = []
    if values["bureau_overdue"] == "thin":
        flags.append("thin_file")
    gap = values["revenue_consistency"]
    if isinstance(gap, Decimal) and gap > revenue_mismatch_share:
        flags.append("revenue_mismatch")
    if values["verification"] == "mismatch":
        flags.append("verification_mismatch")
    if values["cash_gap"] == "gap":
        flags.append("cash_gap")
    if not inp.bureau.available:
        flags.append("bureau_unavailable")
    if inp.mass_address:
        flags.append("mass_address")
    if inp.cashflow.revenue_confirmed is False:
        flags.append("revenue_mismatch")
    return tuple(dict.fromkeys(flags))


def bank_notes(inp: ScoringInput) -> tuple[str, ...]:
    cf = inp.cashflow
    if cf.present and cf.gap_detected and cf.gap_month is not None and cf.gap_amount is not None:
        return (
            f"По выписке прогнозируется кассовый разрыв в {cf.gap_month} на {cf.gap_amount} ₽.",
        )
    return ()


def _growth(now: Decimal | None, previous: Decimal | None) -> Decimal | None:
    if now is None or previous is None or previous <= 0:
        return None
    return (now - previous) / previous


def _debt_load(inp: ScoringInput, revenue: Decimal | None) -> Decimal | None:
    """(платежи по кредитам + оценочный платёж по новому) / средняя месячная выручка."""
    if revenue is None or revenue <= 0:
        return None
    if inp.bureau.available:
        current = inp.bureau.total_monthly_payments
    else:
        current = inp.company.monthly_debt_payments_declared or Decimal(0)
    request = inp.request
    new_payment = estimated_payment(request.amount, request.term_months, request.rate_base)
    return (current + new_payment) / (revenue / _TWELVE)


def _revenue_gap(inp: ScoringInput) -> Decimal | None:
    """Расхождение заявленной выручки с ФНС, доля от заявленной."""
    declared, reported = inp.company.declared_revenue, inp.tax.reported_revenue
    if declared is None or declared <= 0 or reported is None:
        return None
    return abs(declared - reported) / declared


def _industry(okved_main: str, low: frozenset[int], high: frozenset[int]) -> str:
    section = okved_section(okved_main)
    if section in low:
        return "low"
    if section in high:
        return "high"
    return "mid"
