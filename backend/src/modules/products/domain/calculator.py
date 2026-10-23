"""PaymentCalculator — the single payment formula of the system.

Annuity, differentiated and interest-only schedules. Decimal only; every
payment is rounded to kopecks (ROUND_HALF_UP); the last payment takes what is
left, so the principal always adds up to the loan amount exactly.

    monthly rate     r = rate / 12 / 100
    annuity          A = round(P · r / (1 − (1 + r)^−n)),   r = 0: A = round(P / n)
    interest of k    I_k = round(B_{k−1} · rate / 1200)
    principal of k   annuity: A − I_k;  differentiated: round(P / n);  interest-only: 0
    last payment     principal = the remaining balance
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, localcontext

from src.core.domain import Money
from src.modules.products.domain.value_objects import MAX_RATE, MAX_TERM_MONTHS, REPAYMENTS, invalid

SUPPORTED_REPAYMENTS: tuple[str, ...] = ("annuity", "differentiated", "interest_only")

_KOPECK = Decimal("0.01")
_ZERO = Decimal("0.00")
# 12 months × 100 %
_MONTHLY_DIVISOR = Decimal(1200)


def _round(value: Decimal) -> Decimal:
    return value.quantize(_KOPECK, rounding=ROUND_HALF_UP)


@dataclass(frozen=True, slots=True)
class Payment:
    number: int
    principal: Money
    interest: Money
    balance_after: Money

    @property
    def total(self) -> Money:
        return self.principal + self.interest


@dataclass(frozen=True, slots=True)
class PaymentSchedule:
    amount: Money
    term_months: int
    rate: Decimal
    repayment: str
    payments: tuple[Payment, ...]

    @property
    def monthly_payment(self) -> Money:
        """The annuity; for other schedules — the first (largest) payment."""
        return self.payments[0].total

    @property
    def total_interest(self) -> Money:
        return sum((p.interest for p in self.payments), Money.zero(self.amount.currency))

    @property
    def total_paid(self) -> Money:
        return self.amount + self.total_interest


class PaymentCalculator:
    def schedule(
        self, amount: Money, term_months: int, rate: Decimal, repayment: str
    ) -> PaymentSchedule:
        self._validate(amount, term_months, rate, repayment)
        loan = amount.amount
        annuity = self.annuity(amount, term_months, rate).amount if repayment == "annuity" else None
        even_share = _round(loan / term_months)
        balance = loan
        payments: list[Payment] = []
        for number in range(1, term_months + 1):
            interest = _round(balance * rate / _MONTHLY_DIVISOR)
            if number == term_months:
                principal = balance
            elif annuity is not None:
                principal = min(max(annuity - interest, _ZERO), balance)
            elif repayment == "differentiated":
                principal = min(even_share, balance)
            else:
                principal = _ZERO
            balance -= principal
            payments.append(
                Payment(
                    number=number,
                    principal=Money(principal, amount.currency),
                    interest=Money(interest, amount.currency),
                    balance_after=Money(balance, amount.currency),
                )
            )
        return PaymentSchedule(amount, term_months, rate, repayment, tuple(payments))

    def annuity(self, amount: Money, term_months: int, rate: Decimal) -> Money:
        self._validate(amount, term_months, rate, "annuity")
        loan = amount.amount
        with localcontext() as context:
            context.prec = 50
            if rate == 0:
                value = loan / term_months
            else:
                monthly = rate / _MONTHLY_DIVISOR
                value = loan * monthly / (1 - (1 + monthly) ** -term_months)
            return Money(_round(value), amount.currency)

    @staticmethod
    def _validate(amount: Money, term_months: int, rate: Decimal, repayment: str) -> None:
        if not amount.amount > 0:
            raise invalid("amount", "not_positive", "Amount must be positive")
        if not 1 <= term_months <= MAX_TERM_MONTHS:
            raise invalid("term_months", "out_of_range", "Term is out of range")
        if not isinstance(rate, Decimal):
            raise invalid("rate", "not_decimal", "Rate must be a Decimal")
        if not 0 <= rate <= MAX_RATE:
            raise invalid("rate", "out_of_range", "Rate is out of range")
        if repayment not in REPAYMENTS:
            raise invalid("repayment", "unknown", "Unknown repayment schedule")
        if repayment not in SUPPORTED_REPAYMENTS:
            raise invalid(
                "repayment", "unsupported", "This schedule is set by the contract, not a formula"
            )
