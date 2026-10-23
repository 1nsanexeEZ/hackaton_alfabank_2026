from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal, TypeAlias
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.modules.clients.application.dto.reports import SubmitReportDTO

Amount: TypeAlias = Annotated[Decimal, Field(ge=0, max_digits=18, decimal_places=2)]
SignedAmount: TypeAlias = Annotated[Decimal, Field(max_digits=18, decimal_places=2)]


class FinancialReportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    period_year: int
    period_quarter: int | None
    source: Literal["declared", "fns", "bank_statement"]
    revenue: Decimal
    expenses: Decimal | None
    net_profit: Decimal | None
    total_liabilities: Decimal | None
    monthly_debt_payments: Decimal | None
    submitted_by: UUID | None
    submitted_at: datetime


class FinancialReportCreate(BaseModel):
    """Declared figures in roubles for a year (`period_quarter` empty) or a quarter."""

    period_year: int = Field(ge=2000, le=2100)
    period_quarter: int | None = Field(default=None, ge=1, le=4)
    revenue: Amount
    expenses: Amount | None = None
    net_profit: SignedAmount | None = None
    total_liabilities: Amount | None = None
    monthly_debt_payments: Amount | None = None

    def to_dto(self) -> SubmitReportDTO:
        return SubmitReportDTO(
            period_year=self.period_year,
            period_quarter=self.period_quarter,
            revenue=self.revenue,
            expenses=self.expenses,
            net_profit=self.net_profit,
            total_liabilities=self.total_liabilities,
            monthly_debt_payments=self.monthly_debt_payments,
        )
