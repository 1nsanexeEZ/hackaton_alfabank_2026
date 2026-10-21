"""Golden schedules in tests/products/golden were computed independently of the
calculator: exact rational arithmetic (fractions.Fraction) of the annuity
formula, rounding half up to kopecks, the last payment taking the rest."""

import json
from decimal import Decimal
from pathlib import Path

import pytest

from src.core.domain import Money
from src.core.exceptions.exceptions import ValidationError
from src.products.domain.calculator import PaymentCalculator, PaymentSchedule

GOLDEN = Path(__file__).parent.parent / "golden"
calculator = PaymentCalculator()


def schedule(amount: str, term: int, rate: str, repayment: str = "annuity") -> PaymentSchedule:
    return calculator.schedule(Money.of(amount), term, Decimal(rate), repayment)


def as_json(result: PaymentSchedule) -> dict:
    return {
        "amount": str(result.amount.amount),
        "term_months": result.term_months,
        "rate": str(result.rate),
        "repayment": result.repayment,
        "monthly_payment": str(result.monthly_payment.amount),
        "total_interest": str(result.total_interest.amount),
        "total_paid": str(result.total_paid.amount),
        "payments": [
            {
                "number": p.number,
                "principal": str(p.principal.amount),
                "interest": str(p.interest.amount),
                "total": str(p.total.amount),
                "balance_after": str(p.balance_after.amount),
            }
            for p in result.payments
        ],
    }


@pytest.mark.parametrize("path", sorted(GOLDEN.glob("*.json")), ids=lambda p: p.stem)
def test_golden_annuity_schedules(path: Path) -> None:
    golden = json.loads(path.read_text(encoding="utf-8"))
    result = schedule(golden["amount"], golden["term_months"], golden["rate"], golden["repayment"])
    assert as_json(result) == golden


def test_there_are_three_golden_schedules() -> None:
    assert len(list(GOLDEN.glob("*.json"))) == 3


def test_annuity_matches_the_shared_formula() -> None:
    # The same figure the products fake and its contract test use.
    assert schedule("3000000", 24, "24").monthly_payment == Money("158613.29")
    assert calculator.annuity(Money.of(3_000_000), 24, Decimal("24")) == Money("158613.29")


@pytest.mark.parametrize("repayment", ["annuity", "differentiated", "interest_only"])
@pytest.mark.parametrize(
    "amount,term,rate",
    [
        ("300000", 12, "23.5"),
        ("1000000.01", 7, "30"),
        ("5000000", 60, "21.5"),
        ("150000000", 120, "27"),
        ("100000", 3, "24"),
        ("777777.77", 1, "12"),
        ("1234567.89", 36, "0"),
    ],
)
def test_principal_adds_up_to_the_loan(amount: str, term: int, rate: str, repayment: str) -> None:
    result = schedule(amount, term, rate, repayment)
    assert len(result.payments) == term
    assert sum(p.principal.amount for p in result.payments) == Decimal(amount)
    assert result.payments[-1].balance_after == Money.zero()
    assert all(p.principal.amount >= 0 and p.interest.amount >= 0 for p in result.payments)
    assert result.total_paid.amount == sum(p.total.amount for p in result.payments)
    assert result.total_paid == result.amount + result.total_interest
    for p in result.payments:
        assert p.principal.amount == p.principal.amount.quantize(Decimal("0.01"))


def test_zero_rate_has_no_interest() -> None:
    result = schedule("1000000", 3, "0")
    assert [p.total for p in result.payments] == [
        Money("333333.33"),
        Money("333333.33"),
        Money("333333.34"),
    ]
    assert result.total_interest == Money.zero()
    assert calculator.annuity(Money.of(1_200_000), 12, Decimal("0")) == Money.of(100_000)


def test_differentiated_pays_equal_principal_and_falling_interest() -> None:
    # 1 200 000 for 12 months at 12 %: 100 000 of principal, 1 % of the balance a month.
    result = schedule("1200000", 12, "12", "differentiated")
    assert {p.principal for p in result.payments} == {Money.of(100_000)}
    assert result.payments[0].interest == Money.of(12_000)
    assert result.payments[1].interest == Money.of(11_000)
    assert result.payments[-1].interest == Money.of(1_000)
    assert result.monthly_payment == Money.of(112_000)  # the first, largest payment
    assert result.total_interest == Money.of(78_000)
    totals = [p.total for p in result.payments]
    assert totals == sorted(totals, key=lambda m: m.amount, reverse=True)


def test_interest_only_returns_the_principal_at_the_end() -> None:
    result = schedule("1000000", 6, "24", "interest_only")
    assert [p.principal for p in result.payments[:-1]] == [Money.zero()] * 5
    assert result.payments[-1].principal == Money.of(1_000_000)
    assert {p.interest for p in result.payments} == {Money.of(20_000)}
    assert result.monthly_payment == Money.of(20_000)
    assert result.total_interest == Money.of(120_000)


def test_rounding_is_half_up() -> None:
    # 100 000.50 × 1 % = 1 000.005 -> 1 000.01
    result = schedule("100000.50", 2, "12", "interest_only")
    assert result.payments[0].interest == Money("1000.01")


def test_one_month_loan() -> None:
    result = schedule("1000000", 1, "24")
    assert result.payments[0].principal == Money.of(1_000_000)
    assert result.payments[0].interest == Money.of(20_000)
    assert result.monthly_payment == Money.of(1_020_000)


@pytest.mark.parametrize(
    "amount,term,rate,repayment,field",
    [
        ("0", 12, "10", "annuity", "amount"),
        ("-1", 12, "10", "annuity", "amount"),
        ("1000", 0, "10", "annuity", "term_months"),
        ("1000", 361, "10", "annuity", "term_months"),
        ("1000", 12, "-1", "annuity", "rate"),
        ("1000", 12, "101", "annuity", "rate"),
        ("1000", 12, "10", "balloon", "repayment"),
        ("1000", 12, "10", "by_contract_schedule", "repayment"),
    ],
)
def test_invalid_input(amount: str, term: int, rate: str, repayment: str, field: str) -> None:
    with pytest.raises(ValidationError) as error:
        schedule(amount, term, rate, repayment)
    assert error.value.details is not None and error.value.details["field"] == field


def test_float_rate_is_refused() -> None:
    with pytest.raises(ValidationError):
        calculator.schedule(Money.of(1000), 12, 10.5, "annuity")  # type: ignore[arg-type]
