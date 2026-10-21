from __future__ import annotations

import pytest

from app.inn import validate_inn
from tests.conftest import DEMO_INNS


@pytest.mark.parametrize("inn", DEMO_INNS)
def test_demo_inns_are_valid(inn: str) -> None:
    assert validate_inn(inn) is True


@pytest.mark.parametrize(
    "inn",
    ["", "123", "abcdefghij", "1234567890", "770669871600", "77011588170"],
)
def test_invalid_inns_rejected(inn: str) -> None:
    assert validate_inn(inn) is False
