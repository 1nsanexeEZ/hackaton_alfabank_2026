"""Financial reports of a company for the companies API."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Self
from uuid import UUID

from src.core.domain import Money
from src.modules.clients.domain.financial_report import FinancialReport


def amount(value: Money | None) -> Decimal | None:
    return value.amount if value is not None else None


@dataclass(frozen=True, slots=True)
class FinancialReportRecordDTO:
    id: UUID
    period_year: int
    period_quarter: int | None
    source: str
    revenue: Decimal
    expenses: Decimal | None
    net_profit: Decimal | None
    total_liabilities: Decimal | None
    monthly_debt_payments: Decimal | None
    submitted_by: UUID | None
    submitted_at: datetime

    @classmethod
    def of(cls, report: FinancialReport) -> Self:
        figures = report.figures
        return cls(
            id=report.id,
            period_year=report.period.year,
            period_quarter=report.period.quarter,
            source=report.source.value,
            revenue=figures.revenue.amount,
            expenses=amount(figures.expenses),
            net_profit=amount(figures.net_profit),
            total_liabilities=amount(figures.total_liabilities),
            monthly_debt_payments=amount(figures.monthly_debt_payments),
            submitted_by=report.submitted_by,
            submitted_at=report.submitted_at,
        )


@dataclass(frozen=True, slots=True)
class SubmitReportDTO:
    """Declared figures in roubles for a year (`period_quarter` None) or a quarter."""

    period_year: int
    period_quarter: int | None
    revenue: Decimal
    expenses: Decimal | None = None
    net_profit: Decimal | None = None
    total_liabilities: Decimal | None = None
    monthly_debt_payments: Decimal | None = None
