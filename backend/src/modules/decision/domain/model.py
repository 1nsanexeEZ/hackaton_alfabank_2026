"""Язык решения: вход политики, коды причин, трасса правил и итог.

Чистый Python: вход собирает слой application из фасадов соседей, политика (`policy.py`)
считает по нему решение без IO. Суммы и ставки — `Decimal`, ставка — в процентах годовых.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Literal

Outcome = Literal["APPROVE", "COUNTER_OFFER", "REQUEST_INFO", "MANUAL_REVIEW", "REJECT"]
Grade = Literal["A", "B", "C", "D", "E"]


class ReasonCode(StrEnum):
    """Внутренние причины решения; у каждой есть текст для клиента в `explanations_ru.yaml`."""

    STOP_LIQUIDATION = "STOP_LIQUIDATION"
    STOP_BANKRUPTCY = "STOP_BANKRUPTCY"
    STOP_DISQUALIFIED_HEAD = "STOP_DISQUALIFIED_HEAD"
    STOP_OVERDUE_90 = "STOP_OVERDUE_90"
    STOP_GRADE_E = "STOP_GRADE_E"
    # policy_v2: ГИР БО, Контур, ФНС, БКИ руководителя и стоп-лист банка.
    STOP_CURRENT_OVERDUE = "STOP_CURRENT_OVERDUE"
    STOP_HEAD_OVERDUE = "STOP_HEAD_OVERDUE"
    STOP_ACCOUNT_BLOCKS = "STOP_ACCOUNT_BLOCKS"
    STOP_TAX_ARREARS = "STOP_TAX_ARREARS"
    STOP_BANKRUPTCY_MESSAGE = "STOP_BANKRUPTCY_MESSAGE"
    STOP_LARGE_ENFORCEMENT = "STOP_LARGE_ENFORCEMENT"
    STOP_LARGE_LAWSUITS = "STOP_LARGE_LAWSUITS"
    STOP_NEGATIVE_EQUITY = "STOP_NEGATIVE_EQUITY"
    STOP_MASS_ADDRESS = "STOP_MASS_ADDRESS"
    STOP_FORBIDDEN_OKVED = "STOP_FORBIDDEN_OKVED"
    INFO_REVENUE_NOT_CONFIRMED = "INFO_REVENUE_NOT_CONFIRMED"
    LIMIT_BY_PRODUCT = "LIMIT_BY_PRODUCT"
    LIMIT_BY_REVENUE = "LIMIT_BY_REVENUE"
    LIMIT_BY_LTV = "LIMIT_BY_LTV"
    LIMIT_BY_PAYMENT_CAPACITY = "LIMIT_BY_PAYMENT_CAPACITY"
    LIMIT_BELOW_PRODUCT_MIN = "LIMIT_BELOW_PRODUCT_MIN"
    TERM_ADJUSTED = "TERM_ADJUSTED"
    ROUTE_AMOUNT_OVER_AUTO_LIMIT = "ROUTE_AMOUNT_OVER_AUTO_LIMIT"
    ROUTE_GRADE_D = "ROUTE_GRADE_D"
    ROUTE_VERIFICATION_MISMATCH = "ROUTE_VERIFICATION_MISMATCH"
    ROUTE_REVENUE_MISMATCH = "ROUTE_REVENUE_MISMATCH"
    ROUTE_SOURCES_FAILED = "ROUTE_SOURCES_FAILED"
    ROUTE_MASS_ADDRESS = "ROUTE_MASS_ADDRESS"
    ROUTE_TAX_ARREARS = "ROUTE_TAX_ARREARS"
    CASH_GAP_FORECAST = "CASH_GAP_FORECAST"


# --- вход политики -----------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SupportProgramInput:
    code: str
    rate_cap: Decimal
    msp_registry_required: bool
    okved_whitelist: frozenset[str]  # двузначные классы ОКВЭД


@dataclass(frozen=True, slots=True)
class ProductInput:
    """Рамки продукта — из копии условий в заявке (на момент подачи)."""

    code: str
    amount_min: Decimal
    amount_max: Decimal
    term_min_months: int
    term_max_months: int
    rate_base: Decimal
    rate_max: Decimal
    repayment_options: tuple[str, ...]
    collateral_required: bool
    auto_decision_limit: Decimal
    support_program: SupportProgramInput | None = None
    guarantee: str = "none"  # none | owner | msp_corporation
    target_use_confirmation: bool = False


@dataclass(frozen=True, slots=True)
class RequestInput:
    amount: Decimal
    term_months: int


@dataclass(frozen=True, slots=True)
class CompanyInput:
    legal_form: str
    okved_main: str
    registry_status: str  # по ЕГРЮЛ, если источник ответил, иначе из профиля компании
    verification_status: str
    declared_revenue: Decimal | None  # последний годовой отчёт
    declared_expenses: Decimal | None
    reported_revenue: Decimal | None  # ФНС
    disqualified_head: bool | None  # None — ФНС не ответила
    in_msp_registry: bool | None
    mass_address: bool = False
    tax_arrears: Decimal | None = None  # ФНС; None — не ответила
    account_blocks: int | None = None  # решений о блокировке счетов; None — ФНС не ответила


@dataclass(frozen=True, slots=True)
class BureauInput:
    available: bool
    max_overdue_days: int | None  # максимум из текущей и за 12 месяцев
    monthly_payments: Decimal  # платежи по действующим кредитам
    current_overdue_days: int | None = None  # текущая просрочка; None — БКИ не ответило


HeadBureauStatus = Literal["ok", "no_consent", "no_head", "failed", "not_requested"]


@dataclass(frozen=True, slots=True)
class HeadBureauInput:
    """БКИ руководителя по реестру: запрашивается только с его личным согласием."""

    status: HeadBureauStatus
    current_overdue_days: int | None = None  # только при status = ok


@dataclass(frozen=True, slots=True)
class CounterpartyInput:
    """Контур: суды, приставы, банкротство. Суммы — рубли."""

    bankruptcy_messages: int
    enforcement_sum: Decimal  # действующие исполнительные производства
    lawsuits_sum: Decimal  # иски к компании как к ответчику


@dataclass(frozen=True, slots=True)
class AccountingInput:
    """ГИР БО, последний период отчётности."""

    year: int
    revenue: Decimal
    equity: Decimal


@dataclass(frozen=True, slots=True)
class CashflowInput:
    """Сводка прогноза по выписке (enrichment): поток, разрыв, сверка выручки."""

    average_monthly_net: Decimal
    gap_detected: bool
    gap_month: str | None  # YYYY-MM
    revenue_confirmed: bool | None


@dataclass(frozen=True, slots=True)
class CollateralInput:
    type: str  # real_estate | vehicle | equipment | goods
    value: Decimal


@dataclass(frozen=True, slots=True)
class ScoreInput:
    score: int
    grade: Grade
    flags: frozenset[str]
    client_hints: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AlternativeInput:
    """Продукт-кандидат в альтернативу: прошла ли компания его eligibility."""

    code: str
    eligible: bool
    amount_min: Decimal


@dataclass(frozen=True, slots=True)
class DecisionInput:
    product: ProductInput
    request: RequestInput
    company: CompanyInput
    score: ScoreInput | None  # None — результата скоринга нет
    bureau: BureauInput
    cashflow: CashflowInput | None
    collateral: CollateralInput | None
    sources_failed: tuple[str, ...]
    # Закрытый дозапрос с выпиской уже был — повторно выручку не запрашиваем.
    revenue_info_requested: bool
    alternatives: tuple[AlternativeInput, ...] = ()
    counterparty: CounterpartyInput | None = None  # None — Контур не ответил или не запрошен
    accounting: AccountingInput | None = None  # None — отчётности в ГИР БО нет
    head_bureau: HeadBureauInput | None = None


@dataclass(frozen=True, slots=True)
class PreApprovalInput:
    """Облегчённые данные для предодобрения: оценка скоринга без БКИ и выписок."""

    product: ProductInput
    grade: Grade
    score: int
    registry_status: str
    annual_revenue: Decimal | None
    okved_main: str
    in_msp_registry: bool | None = None


# --- итог ----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RuleHit:
    rule: str
    matched: bool
    detail: str


@dataclass(frozen=True, slots=True)
class Limits:
    by_product: Decimal | None = None
    by_revenue: Decimal | None = None
    by_ltv: Decimal | None = None
    by_capacity: Decimal | None = None  # при запрошенном сроке
    final: Decimal | None = None


@dataclass(frozen=True, slots=True)
class OfferTerms:
    """Условия оффера; ежемесячный платёж считает products.calculate_payment."""

    amount: Decimal
    term_months: int
    rate: Decimal
    schedule_type: str
    conditions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class InfoNeed:
    fields: tuple[str, ...]
    documents: tuple[str, ...]
    comment: str


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    policy_version: str
    key_rate: Decimal
    outcome: Outcome
    terms: OfferTerms | None
    alternative_product_code: str | None
    reason_codes: tuple[ReasonCode, ...]
    client_explanation: str
    improvement_hints: tuple[str, ...]
    requested_info: InfoNeed | None
    rule_trace: tuple[RuleHit, ...]
    limits: Limits
    rate: Decimal | None = None


@dataclass(frozen=True, slots=True)
class PreApproval:
    product_code: str
    max_amount: Decimal
    rate_from: Decimal
    term_max_months: int
    factors_summary: tuple[str, ...]
