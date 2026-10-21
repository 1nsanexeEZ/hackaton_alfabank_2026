from decimal import Decimal

import pytest

from src.core.domain import Money


def test_rounds_to_kopecks_half_up() -> None:
    assert Money.of("10.005").amount == Decimal("10.01")
    assert Money.of("10.004").amount == Decimal("10.00")
    assert Money.of("-10.005").amount == Decimal("-10.01")


def test_float_is_rejected() -> None:
    with pytest.raises(TypeError):
        Money(0.1)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        Money.of(1) * 1.5  # type: ignore[operator]


def test_arithmetic_keeps_precision() -> None:
    total = Money.of("0.10") + Money.of("0.20")
    assert total == Money.of("0.30")
    assert Money.of(100) - Money.of("0.01") == Money.of("99.99")
    assert Money.of("33.33") * 3 == Money.of("99.99")
    assert 2 * Money.of(5) == Money.of(10)
    assert -Money.of(5) == Money.of(-5)


def test_comparison_and_flags() -> None:
    assert Money.of(1) < Money.of(2) <= Money.of(2)
    assert Money.of(3) > Money.of(2) >= Money.of(2)
    assert Money.zero().is_zero
    assert Money.of(-1).is_negative
    assert str(Money.of("1500.5")) == "1500.50 RUB"


def test_currencies_do_not_mix() -> None:
    with pytest.raises(ValueError, match="Currency mismatch"):
        Money.of(1) + Money.of(1, "USD")
    with pytest.raises(ValueError, match="Currency mismatch"):
        _ = Money.of(1) < Money.of(1, "USD")


def test_invalid_currency_code() -> None:
    with pytest.raises(ValueError):
        Money.of(1, "rub")
