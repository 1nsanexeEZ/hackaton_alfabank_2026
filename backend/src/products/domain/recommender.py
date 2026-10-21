"""ProductRecommender — deterministic product matching with reasons.

purpose → frames (amount, term) → eligibility of the borrower → rate.
Every recommendation carries reasons in words: the bank must see why a
product was offered. Products the borrower can't get are listed last with
the failed conditions; frames that don't fit come with an adjustment
("максимум 5 млн ₽ — запросите 5 млн ₽ или выберите …"). A cash gap (the
purpose or the scoring forecast) lifts the credit line and the overdraft.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from src.core.domain import Money
from src.products.domain import texts
from src.products.domain.calculator import PaymentCalculator
from src.products.domain.product import CreditProduct
from src.products.domain.value_objects import (
    BorrowerProfile,
    EligibilityCheck,
    EligibilityReason,
    LoanNeed,
)

RecommendationStatus = Literal["available", "needs_adjustment", "unavailable"]

CASH_GAP = "cash_gap"


@dataclass(frozen=True, slots=True)
class Recommendation:
    product: CreditProduct
    rank: int
    # None — no borrower given, eligibility not checked.
    eligibility: EligibilityCheck | None
    fits: bool
    reasons: tuple[EligibilityReason, ...]
    adjustments: tuple[str, ...]
    # The estimate is for the nearest amount and term the product allows.
    repayment: str
    amount: Money
    term_months: int
    monthly_payment_from: Money
    monthly_payment_to: Money

    @property
    def eligible(self) -> bool | None:
        return None if self.eligibility is None else self.eligibility.eligible

    @property
    def status(self) -> RecommendationStatus:
        if self.eligible is False:
            return "unavailable"
        return "available" if self.fits else "needs_adjustment"


class ProductRecommender:
    def __init__(self, calculator: PaymentCalculator | None = None) -> None:
        self._calculator = calculator or PaymentCalculator()

    def recommend(
        self,
        products: Iterable[CreditProduct],
        need: LoanNeed,
        borrower: BorrowerProfile | None = None,
    ) -> list[Recommendation]:
        cash_gap_forecast = borrower is not None and borrower.cash_gap_expected is True
        cash_gap = need.purpose == CASH_GAP or cash_gap_forecast
        candidates = [
            p
            for p in products
            if p.is_selectable
            and (p.serves(need.purpose) or (cash_gap_forecast and p.serves(CASH_GAP)))
        ]
        checks = {
            p.code.value: None if borrower is None else p.check_eligibility(borrower)
            for p in candidates
        }

        def is_eligible(product: CreditProduct) -> bool:
            check = checks[product.code.value]
            return check is None or check.eligible

        def order(product: CreditProduct) -> tuple[int, int, Decimal, int, str]:
            fits = product.fits(need.amount, need.term_months)
            group = 0 if is_eligible(product) and fits else 1 if is_eligible(product) else 2
            lifted = 0 if cash_gap and product.serves(CASH_GAP) else 1
            return (group, lifted, product.client_rate.base, product.sort_order, product.code.value)

        ranked = sorted(candidates, key=order)
        alternatives = [p for p in ranked if is_eligible(p)]
        return [
            self._recommendation(
                rank, product, need, checks[product.code.value], alternatives, cash_gap_forecast
            )
            for rank, product in enumerate(ranked, start=1)
        ]

    def _recommendation(
        self,
        rank: int,
        product: CreditProduct,
        need: LoanNeed,
        check: EligibilityCheck | None,
        alternatives: list[CreditProduct],
        cash_gap_forecast: bool,
    ) -> Recommendation:
        reasons: list[EligibilityReason] = []
        if product.serves(need.purpose):
            title = texts.PURPOSE_TITLES[need.purpose]
            reasons.append(EligibilityReason("purpose", True, f"Подходит для цели «{title}»"))
        if product.serves(CASH_GAP) and (need.purpose == CASH_GAP or cash_gap_forecast):
            reasons.append(_cash_gap_reason(cash_gap_forecast))
        amount_reason = _amount_reason(product, need, alternatives)
        term_reason = _term_reason(product, need, alternatives)
        reasons += [amount_reason, term_reason]
        if check is not None:
            reasons += check.reasons
        collateral = _collateral_reason(product)
        if collateral is not None:
            reasons.append(collateral)
        reasons += [_rate_reason(product), _decision_reason(product, need)]

        amount = product.amount.clamp(need.amount)
        term = product.term.clamp(need.term_months)
        rates = product.client_rate
        repayment = product.default_repayment
        payment_from = self._calculator.schedule(amount, term, rates.base, repayment)
        payment_to = self._calculator.schedule(amount, term, rates.max, repayment)
        return Recommendation(
            product=product,
            rank=rank,
            eligibility=check,
            fits=product.fits(need.amount, need.term_months),
            reasons=tuple(reasons),
            adjustments=tuple(r.message for r in (amount_reason, term_reason) if not r.passed),
            repayment=repayment,
            amount=amount,
            term_months=term,
            monthly_payment_from=payment_from.monthly_payment,
            monthly_payment_to=payment_to.monthly_payment,
        )


def _cash_gap_reason(forecast: bool) -> EligibilityReason:
    why = "По движению денег прогнозируется кассовый разрыв" if forecast else "Нужно закрыть разрыв"
    return EligibilityReason(
        CASH_GAP,
        True,
        f"{why}: деньги берутся по мере нужды и гасятся из поступлений, "
        "поэтому продукт выше в списке",
    )


def _alternative(
    alternatives: list[CreditProduct],
    product: CreditProduct,
    fits: Callable[[CreditProduct], bool],
    detail: Callable[[CreditProduct], str],
    prefix: str = "",
) -> str:
    """The best ranked product the borrower can get that fits where this one doesn't."""
    for other in alternatives:
        if other is not product and fits(other):
            return f" или {prefix}«{other.name}» ({detail(other)})"
    return ""


def _amount_reason(
    product: CreditProduct, need: LoanNeed, alternatives: list[CreditProduct]
) -> EligibilityReason:
    frame = product.amount
    asked = need.amount
    if frame.contains(asked):
        return EligibilityReason(
            "amount",
            True,
            f"Сумма {texts.money(asked)} в рамках продукта: "
            f"от {texts.money(frame.min)} до {texts.money(frame.max)}",
        )

    def fits(other: CreditProduct) -> bool:
        return other.amount.contains(asked)

    if asked > frame.max:
        limit = texts.money(frame.max)
        other = _alternative(
            alternatives, product, fits, lambda p: f"до {texts.money(p.amount.max)}", "выберите "
        )
        message = f"Максимум {limit} — запросите {limit}{other}"
    else:
        limit = texts.money(frame.min)
        other = _alternative(
            alternatives, product, fits, lambda p: f"от {texts.money(p.amount.min)}", "выберите "
        )
        message = f"Минимум {limit} — запросите от {limit}{other}"
    return EligibilityReason("amount", False, message)


def _term_reason(
    product: CreditProduct, need: LoanNeed, alternatives: list[CreditProduct]
) -> EligibilityReason:
    frame = product.term
    asked = need.term_months
    frame_text = f"от {frame.min_months} до {frame.max_months} мес."
    if frame.contains(asked):
        return EligibilityReason("term", True, f"Срок {asked} мес. в рамках продукта: {frame_text}")
    other = _alternative(
        alternatives,
        product,
        lambda p: p.term.contains(asked),
        lambda p: f"от {p.term.min_months} до {p.term.max_months} мес.",
    )
    return EligibilityReason(
        "term",
        False,
        f"Срок {frame_text}, а запрошено {asked} мес. — выберите срок в этих рамках{other}",
    )


def _collateral_reason(product: CreditProduct) -> EligibilityReason | None:
    security = product.security
    types = texts.collateral_types(security.collateral_types)
    if security.collateral == "required":
        return EligibilityReason("collateral", True, f"Нужен залог: {types}")
    if security.collateral == "optional":
        message = f"Залог по желанию ({types})"
        if security.required_from is not None:
            message += f", от {texts.money(security.required_from)} — обязателен"
        return EligibilityReason("collateral", True, message)
    return None


def _rate_reason(product: CreditProduct) -> EligibilityReason:
    rates = product.client_rate
    message = f"Ставка от {texts.rate(rates.base)} до {texts.rate(rates.max)} годовых"
    if product.support_program is not None:
        message += " — потолок по программе господдержки"
    return EligibilityReason("rate", True, message)


def _decision_reason(product: CreditProduct, need: LoanNeed) -> EligibilityReason:
    limit = product.processing.auto_decision_limit
    amount = product.amount.clamp(need.amount)
    if limit.is_zero:
        message = "Заявку всегда рассматривает андеррайтер — автоматического решения нет"
    elif product.requires_manual_review(amount):
        message = f"Сумма больше {texts.money(limit)} — заявку рассмотрит андеррайтер"
    else:
        message = f"Сумма до {texts.money(limit)} — решение может быть принято автоматически"
    return EligibilityReason("decision", True, message)
