"""Scorecard — объяснимая балльная модель кредитного риска.

Логика факторов (как считаем значение и в какую корзину оно попадает) живёт здесь, в коде;
баллы корзин, база и пороги грейдов — в конфиге (`ScorecardConfig`, грузится из YAML в
инфраструктуре). Так модель прозрачна и воспроизводима, а калибровка меняется без правки кода.

`calculate` — чистая функция входа: без IO и без `now()`. Все расчёты в `Decimal`.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from src.scoring.domain.model import (
    CashflowInput,
    Direction,
    Factor,
    Grade,
    RiskFlag,
    ScoringInput,
)

_ZERO = Decimal(0)
_SCORE_MIN, _SCORE_MAX = 0, 1000

# Подсказки клиенту по негативным факторам (конкретные числа модели клиенту не показываем).
_CLIENT_HINTS: dict[str, str] = {
    "business_age": "Срок работы бизнеса небольшой — с ростом истории условия станут лучше.",
    "debt_load": "Высокая долговая нагрузка — рассмотрите меньшую сумму или больший срок.",
    "amount_to_revenue": "Сумма велика относительно годовой выручки — попробуйте меньшую.",
    "revenue_consistency": "Расхождение выручки с данными ФНС — приложите выписку по счёту.",
    "bureau_overdue": "В кредитной истории есть просрочки — своевременные платежи улучшат оценку.",
    "bureau_inquiries": "Много недавних кредитных запросов — это временно снижает оценку.",
    "verification": "Данные компании расходятся с реестром — проверьте профиль.",
    "tax_arrears": "Есть налоговая задолженность — погашение улучшит оценку.",
    "cash_gap": "По выписке возможен кассовый разрыв — удобнее овердрафт или кредитная линия.",
}
_MAX_CLIENT_HINTS = 3


@dataclass(frozen=True, slots=True)
class ScorecardConfig:
    version: str
    base: int
    grades: dict[str, int]  # пороги A/B/C/D (E — остаток)
    points: dict[str, dict[str, int]]  # фактор → корзина → баллы
    industry_low: frozenset[int]
    industry_high: frozenset[int]


@dataclass(frozen=True, slots=True)
class ScorecardOutput:
    score: int
    grade: Grade
    factors: tuple[Factor, ...]
    flags: tuple[RiskFlag, ...]
    data_completeness: Decimal
    bank_notes: tuple[str, ...]


class Scorecard:
    def __init__(self, config: ScorecardConfig) -> None:
        self._c = config

    @property
    def version(self) -> str:
        return self._c.version

    def calculate(self, inp: ScoringInput) -> ScorecardOutput:
        factors: list[Factor] = []
        flags: list[RiskFlag] = []
        notes: list[str] = []

        factors.append(self._business_age(inp))
        factors.append(self._revenue_trend(inp))
        factors.append(self._debt_load(inp))
        factors.append(self._bureau_overdue(inp, flags))
        factors.append(self._bureau_inquiries(inp))
        factors.append(self._tax_arrears(inp))
        factors.append(self._industry_risk(inp))
        factors.append(self._amount_to_revenue(inp))
        factors.append(self._revenue_consistency(inp, flags))
        factors.append(self._verification(inp, flags))
        collateral = self._collateral_coverage(inp)
        if collateral is not None:
            factors.append(collateral)
        factors.append(self._cash_gap(inp, flags, notes))

        if not inp.bureau.available:
            flags.append("bureau_unavailable")
        if inp.mass_address:
            flags.append("mass_address")
        if inp.cashflow.revenue_confirmed is False and "revenue_mismatch" not in flags:
            flags.append("revenue_mismatch")

        factors = self._keep_top_hints(factors)
        score = self._clamp(self._c.base + sum(f.points for f in factors))
        completeness = self._completeness(factors)
        return ScorecardOutput(
            score=score,
            grade=self._grade(score),
            factors=tuple(factors),
            flags=tuple(dict.fromkeys(flags)),  # без дублей, порядок сохранён
            data_completeness=completeness,
            bank_notes=tuple(notes),
        )

    # --- факторы ---------------------------------------------------------

    def _business_age(self, inp: ScoringInput) -> Factor:
        m = inp.company.business_age_months
        if m < 12:
            bucket, label = "lt12", "<12"
        elif m < 24:
            bucket, label = "m12_24", "12–24"
        elif m <= 60:
            bucket, label = "m24_60", "24–60"
        else:
            bucket, label = "gt60", ">60"
        return self._factor("business_age", str(m), label, self._p("business_age", bucket))

    def _revenue_trend(self, inp: ScoringInput) -> Factor:
        now, prev = inp.company.declared_revenue, inp.company.declared_revenue_previous
        if now is None or prev is None or prev <= 0:
            return self._missing("revenue_trend", "нет данных")
        growth = (now - prev) / prev
        if growth < Decimal("-0.20"):
            bucket, label = "down20", "<−20%"
        elif growth < 0:
            bucket, label = "down0", "−20…0%"
        elif growth <= Decimal("0.20"):
            bucket, label = "up20", "0…20%"
        else:
            bucket, label = "up_more", ">20%"
        value = f"{(growth * 100).quantize(Decimal('0.1'), ROUND_HALF_UP)}%"
        return self._factor("revenue_trend", value, label, self._p("revenue_trend", bucket))

    def _debt_load(self, inp: ScoringInput) -> Factor:
        revenue = inp.company.declared_revenue or inp.tax.reported_revenue
        if revenue is None or revenue <= 0:
            return self._missing("debt_load", "нет выручки")
        avg_monthly = revenue / 12
        if inp.bureau.available:
            current = inp.bureau.total_monthly_payments
        else:
            current = inp.company.monthly_debt_payments_declared or _ZERO
        new_payment = _annuity(inp.request.amount, inp.request.term_months, inp.request.rate_base)
        ratio = (current + new_payment) / avg_monthly
        if ratio < Decimal("0.2"):
            bucket, label = "lt02", "<0,2"
        elif ratio < Decimal("0.4"):
            bucket, label = "lt04", "0,2–0,4"
        elif ratio <= Decimal("0.6"):
            bucket, label = "lt06", "0,4–0,6"
        else:
            bucket, label = "gt06", ">0,6"
        value = str(ratio.quantize(Decimal("0.01"), ROUND_HALF_UP))
        return self._factor("debt_load", value, label, self._p("debt_load", bucket))

    def _bureau_overdue(self, inp: ScoringInput, flags: list[RiskFlag]) -> Factor:
        if not inp.bureau.available:
            return self._missing("bureau_overdue", "источник недоступен")
        if not inp.bureau.has_history:
            flags.append("thin_file")
            return self._factor(
                "bureau_overdue",
                None,
                "истории нет",
                self._p("bureau_overdue", "thin"),
                has_data=False,
            )
        days = inp.bureau.max_overdue_days_12m or 0
        if days == 0:
            bucket, label = "none", "0"
        elif days <= 30:
            bucket, label = "d1_30", "1–30"
        elif days <= 90:
            bucket, label = "d31_90", "31–90"
        else:
            bucket, label = "d90_plus", ">90"
        return self._factor("bureau_overdue", str(days), label, self._p("bureau_overdue", bucket))

    def _bureau_inquiries(self, inp: ScoringInput) -> Factor:
        if not inp.bureau.available:
            return self._missing("bureau_inquiries", "источник недоступен")
        count = inp.bureau.inquiries_last_30d or 0
        if count <= 2:
            bucket, label = "le2", "≤2"
        elif count <= 5:
            bucket, label = "i3_5", "3–5"
        else:
            bucket, label = "gt5", ">5"
        return self._factor(
            "bureau_inquiries", str(count), label, self._p("bureau_inquiries", bucket)
        )

    def _tax_arrears(self, inp: ScoringInput) -> Factor:
        arrears = inp.tax.tax_arrears
        if arrears is None:
            return self._missing("tax_arrears", "нет данных")
        bucket, label = ("none", "0") if arrears <= 0 else ("any", ">0")
        return self._factor("tax_arrears", str(arrears), label, self._p("tax_arrears", bucket))

    def _industry_risk(self, inp: ScoringInput) -> Factor:
        section = _okved_section(inp.company.okved_main)
        if section in self._c.industry_low:
            bucket, label = "low", "низкий"
        elif section in self._c.industry_high:
            bucket, label = "high", "высокий"
        else:
            bucket, label = "mid", "средний"
        return self._factor(
            "industry_risk", inp.company.okved_main, label, self._p("industry_risk", bucket)
        )

    def _amount_to_revenue(self, inp: ScoringInput) -> Factor:
        revenue = inp.company.declared_revenue or inp.tax.reported_revenue
        if revenue is None or revenue <= 0:
            return self._missing("amount_to_revenue", "нет выручки")
        ratio = inp.request.amount / revenue
        if ratio < Decimal("0.1"):
            bucket, label = "lt01", "<0,1"
        elif ratio < Decimal("0.3"):
            bucket, label = "lt03", "0,1–0,3"
        elif ratio <= Decimal("0.5"):
            bucket, label = "lt05", "0,3–0,5"
        else:
            bucket, label = "gt05", ">0,5"
        value = str(ratio.quantize(Decimal("0.01"), ROUND_HALF_UP))
        return self._factor("amount_to_revenue", value, label, self._p("amount_to_revenue", bucket))

    def _revenue_consistency(self, inp: ScoringInput, flags: list[RiskFlag]) -> Factor:
        declared, reported = inp.company.declared_revenue, inp.tax.reported_revenue
        if declared is None or declared <= 0 or reported is None:
            return self._missing("revenue_consistency", "нет данных")
        diff = abs(declared - reported) / declared
        if diff <= Decimal("0.15"):
            bucket, label = "le15", "≤15%"
        elif diff <= Decimal("0.30"):
            bucket, label = "p15_30", "15–30%"
        else:
            bucket, label = "gt30", ">30%"
            flags.append("revenue_mismatch")
        value = f"{(diff * 100).quantize(Decimal('0.1'), ROUND_HALF_UP)}%"
        return self._factor(
            "revenue_consistency", value, label, self._p("revenue_consistency", bucket)
        )

    def _verification(self, inp: ScoringInput, flags: list[RiskFlag]) -> Factor:
        status = inp.company.verification_status
        if status == "verified":
            bucket, label = "verified", "подтверждена"
        elif status == "mismatch":
            bucket, label = "mismatch", "расхождение"
            flags.append("verification_mismatch")
        else:
            bucket, label = "other", "не подтверждена"
        return self._factor("verification", status, label, self._p("verification", bucket))

    def _collateral_coverage(self, inp: ScoringInput) -> Factor | None:
        value = inp.collateral.declared_value
        if value is None or inp.request.amount <= 0:
            return None
        coverage = value / inp.request.amount
        if coverage >= 2:
            bucket, label = "ge2", "≥2"
        elif coverage >= 1:
            bucket, label = "c1_2", "1–2"
        else:
            bucket, label = "lt1", "<1"
        return self._factor(
            "collateral_coverage",
            str(coverage.quantize(Decimal("0.01"), ROUND_HALF_UP)),
            label,
            self._p("collateral_coverage", bucket),
        )

    def _cash_gap(self, inp: ScoringInput, flags: list[RiskFlag], notes: list[str]) -> Factor:
        cf: CashflowInput = inp.cashflow
        if not cf.present:
            return self._missing("cash_gap", "нет выписки")
        if cf.gap_detected:
            flags.append("cash_gap")
            if cf.gap_month is not None and cf.gap_amount is not None:
                notes.append(
                    f"По выписке прогнозируется кассовый разрыв в {cf.gap_month} "
                    f"на {cf.gap_amount} ₽."
                )
            return self._factor("cash_gap", "разрыв", "прогнозируется", self._p("cash_gap", "gap"))
        return self._factor(
            "cash_gap", "нет разрыва", "не прогнозируется", self._p("cash_gap", "no_gap")
        )

    # --- вспомогательное -------------------------------------------------

    def _p(self, factor: str, bucket: str) -> int:
        return self._c.points[factor][bucket]

    def _factor(
        self, code: str, value: str | None, label: str, points: int, *, has_data: bool = True
    ) -> Factor:
        direction = _direction(points)
        hint = _CLIENT_HINTS.get(code) if direction == "negative" else None
        return Factor(
            code=code,
            value=value,
            bin=label,
            points=points,
            direction=direction,
            client_hint=hint,
            has_data=has_data,
        )

    def _missing(self, code: str, label: str) -> Factor:
        return Factor(
            code=code, value=None, bin=label, points=0, direction="neutral", has_data=False
        )

    def _keep_top_hints(self, factors: list[Factor]) -> list[Factor]:
        """Подсказки клиенту оставляем только у 2–3 самых негативных факторов."""
        ranked = sorted((f for f in factors if f.client_hint is not None), key=lambda f: f.points)
        keep = {id(f) for f in ranked[:_MAX_CLIENT_HINTS]}
        return [f if id(f) in keep or f.client_hint is None else _drop_hint(f) for f in factors]

    def _completeness(self, factors: list[Factor]) -> Decimal:
        if not factors:
            return Decimal("1.000")
        present = sum(1 for f in factors if f.has_data)
        return (Decimal(present) / Decimal(len(factors))).quantize(Decimal("0.001"), ROUND_HALF_UP)

    def _grade(self, score: int) -> Grade:
        if score >= self._c.grades["A"]:
            return "A"
        if score >= self._c.grades["B"]:
            return "B"
        if score >= self._c.grades["C"]:
            return "C"
        if score >= self._c.grades["D"]:
            return "D"
        return "E"

    @staticmethod
    def _clamp(score: int) -> int:
        return max(_SCORE_MIN, min(_SCORE_MAX, score))


def _direction(points: int) -> Direction:
    if points > 0:
        return "positive"
    if points < 0:
        return "negative"
    return "neutral"


def _drop_hint(factor: Factor) -> Factor:
    return Factor(
        code=factor.code,
        value=factor.value,
        bin=factor.bin,
        points=factor.points,
        direction=factor.direction,
        client_hint=None,
        has_data=factor.has_data,
    )


def _okved_section(okved_main: str) -> int:
    head = okved_main.split(".", 1)[0].strip()
    return int(head) if head.isdigit() else -1


def _annuity(amount: Decimal, term_months: int, annual_rate_percent: Decimal) -> Decimal:
    """Оценочный аннуитетный платёж по новому кредиту — консервативная нагрузка, не решение."""
    if term_months <= 0:
        return amount
    monthly_rate = annual_rate_percent / Decimal(100) / Decimal(12)
    if monthly_rate == 0:
        return (amount / term_months).quantize(Decimal("0.01"), ROUND_HALF_UP)
    factor = (1 + monthly_rate) ** term_months
    return (amount * monthly_rate * factor / (factor - 1)).quantize(Decimal("0.01"), ROUND_HALF_UP)
