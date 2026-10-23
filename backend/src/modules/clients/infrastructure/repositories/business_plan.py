"""Business plans: one row per company, the financial model as a JSON document."""

from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.domain import Money
from src.core.exceptions.exceptions import ConflictError
from src.modules.clients.application.interfaces.repositories import BusinessPlanRepository
from src.modules.clients.domain.business_plan import (
    BusinessPlan,
    FinancialModel,
    PlanMonth,
    StateGuarantee,
)
from src.modules.clients.infrastructure.database.models import BusinessPlanModel
from src.modules.clients.infrastructure.repositories.mappers import aware


class SqlAlchemyBusinessPlanRepository(BusinessPlanRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, organization_id: UUID) -> BusinessPlan | None:
        model = await self._session.get(BusinessPlanModel, organization_id)
        if model is None:
            return None
        return BusinessPlan(
            organization_id=model.organization_id,
            summary=model.summary,
            model=_load(model.financial_model),
            submitted_by=model.submitted_by,
            submitted_at=aware(model.submitted_at),
            revision=model.revision,
        )

    async def add(self, plan: BusinessPlan) -> None:
        self._session.add(BusinessPlanModel(**_values(plan)))
        try:
            await self._session.flush()
        except IntegrityError:
            raise ConflictError(
                "The business plan is being submitted already, retry",
                details={"code": "business_plan_exists"},
            ) from None

    async def save(self, plan: BusinessPlan) -> None:
        model = await self._session.get(BusinessPlanModel, plan.organization_id)
        if model is None:
            raise LookupError(f"Business plan of {plan.organization_id} is not stored")
        # The revision read is one below the new one; otherwise somebody revised it meanwhile.
        if model.revision != plan.revision - 1:
            raise ConflictError(
                "The business plan was changed meanwhile, reload it",
                details={"code": "business_plan_conflict"},
            )
        for name, value in _values(plan).items():
            setattr(model, name, value)
        await self._session.flush()


def _values(plan: BusinessPlan) -> dict[str, Any]:
    return {
        "organization_id": plan.organization_id,
        "summary": plan.summary,
        "financial_model": _dump(plan.model),
        "submitted_by": plan.submitted_by,
        "submitted_at": plan.submitted_at,
        "revision": plan.revision,
    }


def _dump(model: FinancialModel) -> dict[str, Any]:
    return {
        "months": [
            {"revenue": str(m.revenue.amount), "expenses": str(m.expenses.amount)}
            for m in model.months
        ],
        "own_funds": str(model.own_funds.amount),
        "collateral_value": str(model.collateral_value.amount),
        "collateral_description": model.collateral_description,
        "guarantee": model.guarantee.value,
        "guarantee_share": str(model.guarantee_share),
        "loan_amount": str(model.loan_amount.amount),
        "loan_term_months": model.loan_term_months,
    }


def _load(raw: dict[str, Any]) -> FinancialModel:
    return FinancialModel(
        months=tuple(
            PlanMonth(Money(Decimal(m["revenue"])), Money(Decimal(m["expenses"])))
            for m in raw["months"]
        ),
        own_funds=Money(Decimal(raw["own_funds"])),
        collateral_value=Money(Decimal(raw["collateral_value"])),
        collateral_description=raw["collateral_description"],
        guarantee=StateGuarantee(raw["guarantee"]),
        guarantee_share=Decimal(raw["guarantee_share"]),
        loan_amount=Money(Decimal(raw["loan_amount"])),
        loan_term_months=int(raw["loan_term_months"]),
    )
