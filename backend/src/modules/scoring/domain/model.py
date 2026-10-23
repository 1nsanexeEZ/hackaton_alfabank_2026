"""Доменные типы scoring: вход (всё, что нужно для расчёта, зафиксировано на момент подачи)
и результат (скор, грейд, факторы с вкладами, флаги, полнота данных).

Чистый Python: ни pydantic, ни IO, ни `now()`. Возраст бизнеса и даты приходят во входе —
иначе расчёт не воспроизводится. Все суммы и доли — `Decimal`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

# scorecard_v1 ставит A–E по баллу; PD-модель (pd_model_v2) — A–J по вероятности дефолта.
Grade = Literal["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"]
Direction = Literal["positive", "negative", "neutral"]
# ЮЛ и ИП с оборотами в банке от 6 месяцев — свои скоркарты, остальные — упрощённая.
Segment = Literal["legal_entity", "entrepreneur", "new_client"]

# Сигналы для decision, которые не сводятся к баллам.
RiskFlag = Literal[
    "revenue_mismatch",
    "verification_mismatch",
    "bureau_unavailable",
    "thin_file",
    "mass_address",
    "cash_gap",
]


@dataclass(frozen=True, slots=True)
class RequestInput:
    amount: Decimal
    term_months: int
    product_code: str
    facility: str
    rate_base: Decimal  # базовая ставка продукта — для оценочного платежа по новому кредиту


@dataclass(frozen=True, slots=True)
class CompanyInput:
    legal_form: str
    business_age_months: int
    okved_main: str
    verification_status: str  # verified | mismatch | unverified
    registry_status: str  # active | liquidating | liquidated | bankrupt
    declared_revenue: Decimal | None
    declared_revenue_previous: Decimal | None
    monthly_debt_payments_declared: Decimal | None


@dataclass(frozen=True, slots=True)
class TaxInput:
    tax_arrears: Decimal | None
    reported_revenue: Decimal | None


@dataclass(frozen=True, slots=True)
class BureauInput:
    available: bool  # False — источник упал (не штрафуем за свой сбой)
    has_history: bool  # есть обязательства/история (иначе thin file)
    max_overdue_days_12m: int | None
    inquiries_last_30d: int | None
    total_monthly_payments: Decimal


@dataclass(frozen=True, slots=True)
class CollateralInput:
    declared_value: Decimal | None  # None — продукт без залога


@dataclass(frozen=True, slots=True)
class CashflowInput:
    present: bool  # были ли выписки
    gap_detected: bool | None
    gap_month: str | None
    gap_amount: Decimal | None
    revenue_confirmed: bool | None


@dataclass(frozen=True, slots=True)
class ScoringInput:
    request: RequestInput
    company: CompanyInput
    tax: TaxInput
    bureau: BureauInput
    collateral: CollateralInput
    cashflow: CashflowInput
    mass_address: bool
    sources_failed: tuple[str, ...]
    as_of: date


@dataclass(frozen=True, slots=True)
class Factor:
    code: str
    value: str | None  # как посчитали, например "0.52"; None — данных не было
    bin: str  # корзина, например "0.4–0.6"
    points: int
    direction: Direction
    client_hint: str | None = None  # подсказка клиенту — только для негативных факторов
    has_data: bool = True  # False — фактор нейтрален из-за отсутствия данных


@dataclass(frozen=True, slots=True)
class MlScore:
    """Оценка ML-модели (`ml_model.py`) — рядом с PD-моделью, на той же шкале грейдов A–J."""

    model_version: str
    pd_12m: Decimal  # вероятность дефолта за 12 месяцев, доля
    score: int
    grade: Grade
    factors: tuple[Factor, ...]
    reason_codes: tuple[str, ...]  # топ-3 признака, снизивших балл, по недобранным баллам


@dataclass(frozen=True, slots=True)
class ScoringResult:
    id: UUID
    application_id: UUID
    requested_by_command: UUID  # команда CalculateScore — ключ идемпотентности
    model_version: str
    score: int
    grade: Grade
    factors: tuple[Factor, ...]
    flags: tuple[RiskFlag, ...]
    data_completeness: Decimal
    computed_at: datetime
    input_hash: str = ""
    bank_notes: tuple[str, ...] = field(
        default_factory=tuple
    )  # пояснения для банка (кассовый разрыв)
    # PD-модель; у результатов scorecard_v1 их нет.
    segment: Segment | None = None
    scorecard: str | None = None
    pd_12m: Decimal | None = None  # доля, 0.0340 — 3,4%
    reason_codes: tuple[str, ...] = ()  # топ-3 признака, снизивших балл, по потере баллов
    # ML-модель (scoring_0003); у результатов до неё — None.
    ml: MlScore | None = None
