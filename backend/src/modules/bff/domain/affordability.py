"""What a company can afford to pay each month, for the calculator.

The same rule as the bank's decision applies: the payment is at most a share of the free
cash flow, the flow is the annual report's profit per month less the payments on current
debts. Only what the company declared is known here, so the figure is a hint, not a limit
the bank binds itself to: the credit bureau and the bank statement can change it.
"""

from decimal import ROUND_DOWN, Decimal

PAYMENT_SHARE = Decimal("0.4")
# The report has no expenses: this share of the revenue is assumed, as the decision does.
ASSUMED_EXPENSE_RATIO = Decimal("0.8")

_MONTHS = Decimal(12)
_CENT = Decimal("0.01")


def monthly_payment_capacity(
    revenue: Decimal, expenses: Decimal | None, debt_payments: Decimal | None
) -> Decimal:
    """The largest monthly payment; zero when the flow does not cover the debts."""
    spent = expenses if expenses is not None else revenue * ASSUMED_EXPENSE_RATIO
    free = (revenue - spent) / _MONTHS - (debt_payments or Decimal(0))
    return max((PAYMENT_SHARE * free).quantize(_CENT, rounding=ROUND_DOWN), Decimal(0))
