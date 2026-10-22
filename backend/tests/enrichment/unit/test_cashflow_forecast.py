from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from src.enrichment.domain.cashflow import Transaction, build_forecast, parse_statement
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


def test_zakat_declining_business_has_gap_at_once() -> None:
    # Поступления падают, в среднем бизнес сжигает деньги: разрыв уже в первом месяце.
    forecast = _forecast("zakat", "300000", "188600", "20000000")
    assert forecast.gap_detected is True
    assert forecast.gap_month == "2026-10"
    assert forecast.gap_amount == Decimal("1965800.01")
    assert forecast.revenue_confirmed is True  # оборот 19 млн из заявленных 20 млн
    assert forecast.annual_inflow == Decimal("19000000.00")


def test_sboy_even_flow_has_no_gap() -> None:
    forecast = _forecast("sboy", "0", "94300", "25000000")
    assert forecast.gap_detected is False
    assert forecast.gap_month is None
    assert forecast.revenue_confirmed is True
    assert forecast.annual_inflow == Decimal("24000000.00")


def test_negative_average_flow_ignores_last_year_good_months() -> None:
    # Средний поток отрицательный: удачный прошлогодний месяц не должен «вытянуть» прогноз.
    transactions = [
        Transaction(txn_date=date(2025, 10, 5), amount=Decimal("500000")),
        Transaction(txn_date=date(2025, 11, 5), amount=Decimal("-900000")),
    ]
    forecast = build_forecast(
        transactions,
        current_monthly_payments=Decimal(0),
        new_loan_payment=Decimal(0),
        declared_annual_revenue=None,
        as_of=_AS_OF,
        statement_document_ids=(uuid4(),),
    )
    # средний чистый поток −200 000 в каждом месяце прогноза
    assert [p.projected_balance for p in forecast.forecast] == [
        Decimal("-200000.00"),
        Decimal("-400000.00"),
        Decimal("-600000.00"),
    ]
