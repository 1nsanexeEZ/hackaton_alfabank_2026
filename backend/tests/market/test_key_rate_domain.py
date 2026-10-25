from datetime import date
from decimal import Decimal

import pytest

from src.modules.market.domain.enums import RateSource
from src.modules.market.domain.exceptions import InvalidKeyRateError
from src.modules.market.domain.key_rate import KeyRate

DAY = date(2026, 12, 21)


def rate(value: str = "13.50", decided_on: date | None = None, note: str | None = None) -> KeyRate:
    return KeyRate(DAY, Decimal(value), RateSource.ADMIN, decided_on=decided_on, note=note)


@pytest.mark.parametrize("value", ["0", "100", "13.5", "21.25"])
def test_value_within_bounds(value: str) -> None:
    assert rate(value).value == Decimal(value).quantize(Decimal("0.01"))


@pytest.mark.parametrize("value", ["-0.01", "100.01", "13.555"])
def test_value_out_of_bounds_or_too_precise(value: str) -> None:
    with pytest.raises(InvalidKeyRateError) as error:
        rate(value)
    assert error.value.details == {"field": "value", "code": "invalid"}


def test_decision_is_on_or_before_the_effective_date() -> None:
    assert rate(decided_on=date(2026, 12, 18)).decided_on == date(2026, 12, 18)
    assert rate(decided_on=DAY).decided_on == DAY
    with pytest.raises(InvalidKeyRateError):
        rate(decided_on=date(2026, 12, 22))


def test_note_is_limited() -> None:
    with pytest.raises(InvalidKeyRateError):
        rate(note="х" * 501)


def test_only_a_rate_not_in_force_yet_or_from_today_is_removable() -> None:
    future = rate()
    assert future.can_be_removed(date(2026, 12, 20))
    assert future.can_be_removed(DAY)
    assert not future.can_be_removed(date(2026, 12, 22))
