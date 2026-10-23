"""Одна формула аннуитета: график клиента, оффер decision и нагрузка скоринга дают одинаковый
платёж на одном входе."""

from decimal import Decimal

import pytest

from src.core.domain import Money
from src.core.domain.annuity import annuity_payment, max_principal
from src.modules.decision.domain import policy
from src.modules.products.domain.calculator import PaymentCalculator
from src.modules.scoring.domain.scorecard import estimated_payment

CASES = [
    ("3000000", 24, "24"),
    ("3000000", 24, "23.50"),
    ("5000000", 60, "27.00"),
    ("30000000", 120, "23.34"),
    ("1200000", 12, "0"),
    ("300000", 1, "30"),
]


def test_known_payment() -> None:
    assert annuity_payment(Decimal("3000000"), 24, Decimal("24")) == Decimal("158613.29")
    assert annuity_payment(Decimal("1200000"), 12, Decimal(0)) == Decimal("100000.00")


@pytest.mark.parametrize(("amount", "term", "rate"), CASES)
def test_products_decision_and_scoring_pay_the_same(amount: str, term: int, rate: str) -> None:
    loan, annual = Decimal(amount), Decimal(rate)
    expected = annuity_payment(loan, term, annual)
    assert PaymentCalculator().annuity(Money(loan), term, annual).amount == expected
    assert policy.annuity_payment(loan, term, annual) == expected
    assert estimated_payment(loan, term, annual) == expected


@pytest.mark.parametrize(("amount", "term", "rate"), CASES)
def test_max_principal_is_the_inverse_rounded_down(amount: str, term: int, rate: str) -> None:
    payment = annuity_payment(Decimal(amount), term, Decimal(rate))
    principal = max_principal(payment, term, Decimal(rate))
    assert annuity_payment(principal, term, Decimal(rate)) <= payment
    assert abs(principal - Decimal(amount)) <= Decimal(term)  # копейки платежа × срок


def test_no_payment_no_principal() -> None:
    assert max_principal(Decimal(0), 24, Decimal("23.5")) == 0
