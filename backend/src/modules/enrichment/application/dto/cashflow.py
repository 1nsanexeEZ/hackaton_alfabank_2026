"""Прогноз кассового разрыва по выпискам — как его видят соседи."""

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID


@dataclass(frozen=True, slots=True)
class CashflowMonthDTO:
    month: str  # YYYY-MM
    inflow: Decimal
    outflow: Decimal
    net: Decimal
    balance: Decimal


@dataclass(frozen=True, slots=True)
class CashflowProjectionDTO:
    month: str  # YYYY-MM
    projected_balance: Decimal


@dataclass(frozen=True, slots=True)
class CashflowForecastDTO:
    months_history: tuple[CashflowMonthDTO, ...]
    forecast: tuple[CashflowProjectionDTO, ...]
    gap_detected: bool
    gap_month: str | None
    gap_amount: Decimal | None
    annual_inflow: Decimal
    revenue_confirmed: bool | None
    method: str
    statement_document_ids: tuple[UUID, ...]
