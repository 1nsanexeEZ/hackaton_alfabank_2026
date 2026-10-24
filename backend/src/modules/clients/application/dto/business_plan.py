"""The business plan and the financial model of a startup for the companies API and the
facade. Re-exported by facade.py."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal, Self, cast
from uuid import UUID

from src.modules.clients.domain.business_plan import BusinessPlan, FinancialModel

StateGuarantee = Literal["none", "msp_corporation", "regional_fund"]


@dataclass(frozen=True, slots=True)
class PlanMonthDTO:
    revenue: Decimal
    expenses: Decimal


@dataclass(frozen=True, slots=True)
class FinancialModelDTO:
    """24 months of revenue and operating expenses, own funds, collateral, a state support
    guarantee and the loan the project needs; roubles."""

    months: tuple[PlanMonthDTO, ...]
    own_funds: Decimal
    collateral_value: Decimal
    collateral_description: str | None
    guarantee: StateGuarantee
    guarantee_share: Decimal
    loan_amount: Decimal
    loan_term_months: int

    @classmethod
    def of(cls, model: FinancialModel) -> Self:
        return cls(
            months=tuple(PlanMonthDTO(m.revenue.amount, m.expenses.amount) for m in model.months),
            own_funds=model.own_funds.amount,
            collateral_value=model.collateral_value.amount,
            collateral_description=model.collateral_description,
            guarantee=cast(StateGuarantee, model.guarantee.value),
            guarantee_share=model.guarantee_share,
            loan_amount=model.loan_amount.amount,
            loan_term_months=model.loan_term_months,
        )


@dataclass(frozen=True, slots=True)
class BusinessPlanDTO:
    organization_id: UUID
    summary: str
    financial_model: FinancialModelDTO
    submitted_by: UUID | None
    submitted_at: datetime
    # Grows with every revision: an assessment names the revision it was made on.
    revision: int

    @classmethod
    def of(cls, plan: BusinessPlan) -> Self:
        return cls(
            organization_id=plan.organization_id,
            summary=plan.summary,
            financial_model=FinancialModelDTO.of(plan.model),
            submitted_by=plan.submitted_by,
            submitted_at=plan.submitted_at,
            revision=plan.revision,
        )


@dataclass(frozen=True, slots=True)
class SubmitBusinessPlanDTO:
    summary: str
    financial_model: FinancialModelDTO
