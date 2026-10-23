"""Annuity — the one payment formula of the system.

The client's schedule (products), the offer payment and the payment-capacity
limit (decision) and the debt load of the scoring models all use it, so a
payment never differs between them by a kopeck.

    monthly rate     r = rate / 12 / 100
    annuity          A = round(P · r / (1 − (1 + r)^−n)),   r = 0: A = round(P / n)
    max principal    P = floor(A · (1 − (1 + r)^−n) / r),   r = 0: P = A · n

Decimal with 50 digits of precision; the payment is rounded to kopecks half
up, the principal down, so that it never needs a larger payment than given.
"""

from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal, localcontext

_KOPECK = Decimal("0.01")
_ZERO = Decimal(0)
# 12 months × 100 %
_MONTHLY_DIVISOR = Decimal(1200)
_PRECISION = 50


def annuity_payment(amount: Decimal, term_months: int, rate: Decimal) -> Decimal:
    """Monthly annuity payment, `rate` in percent per year."""
    with localcontext() as context:
        context.prec = _PRECISION
        if rate == 0:
            value = amount / term_months
        else:
            monthly = rate / _MONTHLY_DIVISOR
            value = amount * monthly / (1 - (1 + monthly) ** -term_months)
        return value.quantize(_KOPECK, rounding=ROUND_HALF_UP)


def max_principal(payment: Decimal, term_months: int, rate: Decimal) -> Decimal:
    """The largest loan whose annuity payment does not exceed `payment`."""
    if payment <= 0:
        return _ZERO
    with localcontext() as context:
        context.prec = _PRECISION
        if rate == 0:
            principal = payment * term_months
        else:
            monthly = rate / _MONTHLY_DIVISOR
            principal = payment * (1 - (1 + monthly) ** -term_months) / monthly
        return principal.quantize(_KOPECK, rounding=ROUND_DOWN)
