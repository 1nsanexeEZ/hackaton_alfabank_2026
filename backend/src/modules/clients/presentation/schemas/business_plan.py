from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal, TypeAlias
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.modules.clients.application.dto.business_plan import (
    FinancialModelDTO,
    PlanMonthDTO,
    SubmitBusinessPlanDTO,
)
from src.modules.clients.domain.business_plan import (
    COLLATERAL_MAX_LENGTH,
    HORIZON_MONTHS,
    SUMMARY_MAX_LENGTH,
)

Amount: TypeAlias = Annotated[Decimal, Field(ge=0, max_digits=18, decimal_places=2)]
Guarantee: TypeAlias = Literal["none", "msp_corporation", "regional_fund"]


class PlanMonth(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    revenue: Amount
    # Operating expenses, without payments on the loan asked for.
    expenses: Amount


class FinancialModel(BaseModel):
    """The bank's template, roubles: revenue and expenses for each of the first 24 months, own
    funds put into the project, collateral (0 — none), a state support guarantee and the loan
    the project needs."""

    model_config = ConfigDict(from_attributes=True)

    months: list[PlanMonth] = Field(min_length=HORIZON_MONTHS, max_length=HORIZON_MONTHS)
    own_funds: Amount
    collateral_value: Amount = Decimal(0)
    collateral_description: str | None = Field(default=None, max_length=COLLATERAL_MAX_LENGTH)
    # Корпорация МСП or a regional guarantee fund; `guarantee_share` — the share of the loan
    # it covers, 0 without a guarantee.
    guarantee: Guarantee = "none"
    guarantee_share: Decimal = Field(default=Decimal(0), ge=0, le=1, decimal_places=4)
    loan_amount: Amount = Field(gt=0)
    loan_term_months: int = Field(ge=1, le=360)

    def to_dto(self) -> FinancialModelDTO:
        return FinancialModelDTO(
            months=tuple(PlanMonthDTO(m.revenue, m.expenses) for m in self.months),
            own_funds=self.own_funds,
            collateral_value=self.collateral_value,
            collateral_description=self.collateral_description,
            guarantee=self.guarantee,
            guarantee_share=self.guarantee_share,
            loan_amount=self.loan_amount,
            loan_term_months=self.loan_term_months,
        )


class BusinessPlanWrite(BaseModel):
    # The project in words: the product, the market, the team, the sales plan.
    summary: str = Field(min_length=1, max_length=SUMMARY_MAX_LENGTH)
    financial_model: FinancialModel

    def to_dto(self) -> SubmitBusinessPlanDTO:
        return SubmitBusinessPlanDTO(
            summary=self.summary, financial_model=self.financial_model.to_dto()
        )


class BusinessPlanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    organization_id: UUID
    summary: str
    financial_model: FinancialModel
    submitted_by: UUID | None
    submitted_at: datetime
    # Grows with every revision; the project assessment names the one it was made on.
    revision: int
