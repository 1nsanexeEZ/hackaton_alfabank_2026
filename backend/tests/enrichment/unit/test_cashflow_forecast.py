from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from src.enrichment.domain.cashflow import build_forecast, parse_statement
from src.enrichment.facade import CashflowForecastDTO

_SEED = Path(__file__).resolve().parents[3] / "seed" / "statements"
_AS_OF = date(2026, 10, 1)


def _forecast(code: str, current: str, new: str, declared: str) -> CashflowForecastDTO:
    transactions = parse_statement((_SEED / f"{code}.csv").read_bytes())
    return build_forecast(
        transactions,
        current_monthly_payments=Decimal(current),
        new_loan_payment=Decimal(new),
        declared_annual_revenue=Decimal(declared),
        as_of=_AS_OF,
        statement_document_ids=(uuid4(),),
    )


def test_romashka_no_gap_and_revenue_confirmed() -> None:
    forecast = _forecast("romashka", "180000", "150000", "48000000")
    assert forecast.gap_detected is False
    assert forecast.revenue_confirmed is True
    assert forecast.annual_inflow == Decimal("48000000.00")
    assert len(forecast.months_history) == 12


def test_ivanov_gap_in_second_forecast_month() -> None:
    forecast = _forecast("ivanov", "0", "254000", "6000000")
    assert forecast.gap_detected is True
    assert forecast.gap_month == "2026-11"
    assert forecast.gap_amount is not None
    assert forecast.revenue_confirmed is True


def test_progress_revenue_not_confirmed() -> None:
    forecast = _forecast("progress", "150000", "400000", "36000000")
    assert forecast.revenue_confirmed is False
    assert forecast.annual_inflow == Decimal("12000000.00")


def test_vector_has_winter_gap() -> None:
    forecast = _forecast("vector", "340000", "250000", "30000000")
    assert forecast.gap_detected is True
    assert forecast.gap_month == "2026-12"


def test_no_declared_revenue_leaves_confirmation_unknown() -> None:
    forecast = _forecast("romashka", "0", "0", "0")
    assert forecast.revenue_confirmed is None
