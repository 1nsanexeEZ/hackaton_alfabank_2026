import pytest

from src.notifications.domain.advice import RULES, advice_for


def codes(signals: list[str], product: str | None = None) -> list[str]:
    return [a.code for a in advice_for(signals, product)]


@pytest.mark.parametrize(
    "signal", ["cash_gap", "cash_gap_forecast", "CASH_GAP_RISK", " liquidity_gap_3m "]
)
def test_flag_spellings_give_the_same_advice(signal: str) -> None:
    assert codes([signal]) == ["cash_gap"]


def test_each_advice_once_in_rule_order() -> None:
    signals = ["revenue_unconfirmed", "cash_gap", "cash_gap_forecast", "tax_arrears", "x"]
    assert codes(signals) == ["cash_gap", "confirm_revenue", "tax_arrears"]


def test_unknown_and_empty_signals_give_nothing() -> None:
    assert codes(["score_low", ""]) == []


@pytest.mark.parametrize("product", ["CREDIT_LINE", "OVERDRAFT"])
def test_no_point_suggesting_the_product_already_asked_for(product: str) -> None:
    assert codes(["cash_gap", "revenue_unconfirmed"], product) == ["confirm_revenue"]


def test_texts_are_plain_and_links_known() -> None:
    for rule in RULES:
        assert "<" not in rule.title + rule.body
        assert rule.link is None or rule.link.startswith("/")
        assert rule.keywords
