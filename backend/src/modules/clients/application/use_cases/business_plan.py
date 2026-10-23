"""The business plan of a startup in the cabinet: typed in by its members before an
application, read by the bank for the project assessment."""

from uuid import UUID

from src.core.access.access_context import AccessContext
from src.core.domain import Money
from src.core.domain.clock import Clock
from src.core.exceptions.exceptions import NotFoundError
from src.core.uow import UnitOfWork
from src.modules.clients.application.dto.business_plan import (
    BusinessPlanDTO,
    FinancialModelDTO,
    SubmitBusinessPlanDTO,
)
from src.modules.clients.application.interfaces.repositories import (
    BusinessPlanRepository,
    OrganizationRepository,
)
from src.modules.clients.application.use_cases.common import (
    actor_of,
    get_organization,
    get_to_change,
)
from src.modules.clients.domain.business_plan import (
    BusinessPlan,
    FinancialModel,
    PlanMonth,
    StateGuarantee,
)
from src.modules.clients.domain.enums import OrgPermission


def financial_model(data: FinancialModelDTO) -> FinancialModel:
    return FinancialModel(
        months=tuple(PlanMonth(Money(m.revenue), Money(m.expenses)) for m in data.months),
        own_funds=Money(data.own_funds),
        collateral_value=Money(data.collateral_value),
        collateral_description=data.collateral_description,
        guarantee=StateGuarantee(data.guarantee),
        guarantee_share=data.guarantee_share,
        loan_amount=Money(data.loan_amount),
        loan_term_months=data.loan_term_months,
    )


class GetBusinessPlanUseCase:
    def __init__(
        self, organizations: OrganizationRepository, plans: BusinessPlanRepository
    ) -> None:
        self._organizations = organizations
        self._plans = plans

    async def execute(self, access: AccessContext, organization_id: UUID) -> BusinessPlanDTO:
        org = await get_organization(self._organizations, organization_id, access)
        plan = await self._plans.get(org.id)
        if plan is None:
            raise NotFoundError("Business plan not found")
        return BusinessPlanDTO.of(plan)


class SubmitBusinessPlanUseCase:
    """A member with `edit_financials` fills in the plan; submitted again, it is revised."""

    def __init__(
        self,
        uow: UnitOfWork,
        organizations: OrganizationRepository,
        plans: BusinessPlanRepository,
        clock: Clock,
    ) -> None:
        self._uow = uow
        self._organizations = organizations
        self._plans = plans
        self._clock = clock

    async def execute(
        self, access: AccessContext, organization_id: UUID, data: SubmitBusinessPlanDTO
    ) -> tuple[BusinessPlanDTO, bool]:
        """The plan and whether it is new (False — revised)."""
        model = financial_model(data.financial_model)
        now = self._clock.now()
        async with self._uow:
            org = await get_to_change(self._organizations, access, organization_id)
            actor = actor_of(access)
            if not actor.is_bank:
                org.ensure_can(access.user_id, OrgPermission.EDIT_FINANCIALS, now)
            plan = await self._plans.get(org.id)
            if plan is None:
                plan = BusinessPlan.submit(
                    organization_id=org.id,
                    summary=data.summary,
                    model=model,
                    submitted_by=actor.account_id,
                    now=now,
                )
                await self._plans.add(plan)
                created = True
            else:
                plan.revise(data.summary, model, actor.account_id, now)
                await self._plans.save(plan)
                created = False
            await self._uow.commit()
        return BusinessPlanDTO.of(plan), created


class FindBusinessPlanUseCase:
    """For the facade: the bank reads the plan without the client's access context."""

    def __init__(self, plans: BusinessPlanRepository) -> None:
        self._plans = plans

    async def execute(self, organization_id: UUID) -> BusinessPlanDTO | None:
        plan = await self._plans.get(organization_id)
        return BusinessPlanDTO.of(plan) if plan is not None else None
