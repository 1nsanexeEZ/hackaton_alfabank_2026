"""FinancialReport — figures of a company for a period from one source.

One report per (company, period, source): a declared report submitted again
for the same period revises the figures instead of adding a second one.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Self
from uuid import UUID

from src.core.domain import Money
from src.core.exceptions.exceptions import ValidationError
from src.modules.clients.domain.enums import ReportSource
from src.modules.clients.domain.events import FinancialReportSubmitted, OrganizationEvent
from src.modules.clients.domain.value_objects import FiscalPeriod


def _invalid(field_name: str, code: str, message: str) -> ValidationError:
    return ValidationError(message, details={"field": field_name, "code": code})


@dataclass(frozen=True, slots=True)
class ReportFigures:
    revenue: Money
    expenses: Money | None = None
    # May be negative (a loss).
    net_profit: Money | None = None
    total_liabilities: Money | None = None
    monthly_debt_payments: Money | None = None

    def __post_init__(self) -> None:
        values = {
            "revenue": self.revenue,
            "expenses": self.expenses,
            "net_profit": self.net_profit,
            "total_liabilities": self.total_liabilities,
            "monthly_debt_payments": self.monthly_debt_payments,
        }
        for name, money in values.items():
            if money is None:
                continue
            if money.currency != self.revenue.currency:
                raise _invalid(name, "currency_mismatch", "All figures must be in one currency")
            if name != "net_profit" and money.is_negative:
                raise _invalid(name, "negative", "Value must not be negative")


class FinancialReport:
    def __init__(
        self,
        *,
        id: UUID,
        organization_id: UUID,
        period: FiscalPeriod,
        source: ReportSource,
        figures: ReportFigures,
        submitted_at: datetime,
        submitted_by: UUID | None = None,
    ) -> None:
        self.id = id
        self.organization_id = organization_id
        self.period = period
        self.source = source
        self.figures = figures
        self.submitted_by = submitted_by
        self.submitted_at = submitted_at
        self._events: list[OrganizationEvent] = []

    @classmethod
    def submit(
        cls,
        *,
        id: UUID,
        organization_id: UUID,
        period: FiscalPeriod,
        source: ReportSource,
        figures: ReportFigures,
        submitted_by: UUID | None,
        now: datetime,
    ) -> Self:
        """Use Organization.submit_financial_report: it checks the rights."""
        _ensure_closed(period, now)
        report = cls(
            id=id,
            organization_id=organization_id,
            period=period,
            source=source,
            figures=figures,
            submitted_by=submitted_by,
            submitted_at=now,
        )
        report._submitted(now)
        return report

    def revise(self, figures: ReportFigures, submitted_by: UUID | None, now: datetime) -> None:
        _ensure_closed(self.period, now)
        self.figures = figures
        self.submitted_by = submitted_by
        self.submitted_at = now
        self._submitted(now)

    def pull_events(self) -> list[OrganizationEvent]:
        events, self._events = self._events, []
        return events

    def _submitted(self, now: datetime) -> None:
        self._events.append(
            FinancialReportSubmitted(
                occurred_at=now,
                organization_id=self.organization_id,
                report_id=self.id,
                period_year=self.period.year,
                period_quarter=self.period.quarter,
                source=self.source.value,
            )
        )


def _ensure_closed(period: FiscalPeriod, now: datetime) -> None:
    if not period.is_closed(now.date()):
        raise ValidationError(
            "The period is not over yet",
            details={"field": "period", "code": "period_not_closed", "period": str(period)},
        )
