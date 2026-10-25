"""Catalog rates follow the key rate: set at CATALOG_KEY_RATE, moved by KEY_RATE minus it."""

from decimal import Decimal

import pytest

from src.core.config import Settings
from src.modules.products.application.services import rate_shift_of
from src.modules.products.domain.value_objects import MAX_RATE, RateRange
from tests.products.factories import catalog_product


def test_key_rate_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KEY_RATE", raising=False)
    monkeypatch.delenv("CATALOG_KEY_RATE", raising=False)
    settings = Settings(_env_file=None)
    assert (settings.key_rate, settings.catalog_key_rate) == (Decimal("14.00"), Decimal("16.50"))
    assert rate_shift_of(settings) == Decimal("-2.50")
    monkeypatch.setenv("KEY_RATE", "18.25")
    assert rate_shift_of(Settings(_env_file=None)) == Decimal("1.75")


def test_rate_range_and_support_cap_move_with_the_key_rate() -> None:
    gov = catalog_product("GOV_SUPPORT")
    moved = gov.at_key_rate(Decimal("-2.5"))
    assert moved.rate == RateRange(Decimal("9.5"), Decimal("15.5"))
    assert moved.support_program is not None and moved.support_program.rate_cap == Decimal("12.5")
    assert moved.client_rate == RateRange(Decimal("9.5"), Decimal("12.5"))
    # The stored product does not change.
    assert gov.rate == RateRange(Decimal("12"), Decimal("18"))
    assert gov.support_program is not None and gov.support_program.rate_cap == Decimal("15")


def test_no_shift_is_the_same_product() -> None:
    unsecured = catalog_product("UNSECURED")
    assert unsecured.at_key_rate(Decimal(0)) is unsecured


def test_moved_rates_stay_within_bounds() -> None:
    gov = catalog_product("GOV_SUPPORT")
    low = gov.at_key_rate(Decimal("-16"))
    assert low.rate == RateRange(Decimal(0), Decimal(2))
    assert low.support_program is not None and low.support_program.rate_cap == Decimal(0)
    assert gov.at_key_rate(Decimal(90)).rate == RateRange(Decimal(100), MAX_RATE)
