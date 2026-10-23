from uuid import UUID

from fastapi import APIRouter, Response, status

from src.modules.clients.presentation.dependencies import (
    GetBusinessPlanDep,
    ReadAccess,
    SubmitBusinessPlanDep,
    UpdateAccess,
)
from src.modules.clients.presentation.schemas.business_plan import (
    BusinessPlanRead,
    BusinessPlanWrite,
)

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.get("/{organization_id}/business-plan", response_model=BusinessPlanRead)
async def get_business_plan(
    organization_id: UUID, access: ReadAccess, use_case: GetBusinessPlanDep
) -> BusinessPlanRead:
    """404 — not filled in yet."""
    return BusinessPlanRead.model_validate(await use_case.execute(access, organization_id))


@router.put("/{organization_id}/business-plan", response_model=BusinessPlanRead)
async def submit_business_plan(
    organization_id: UUID,
    data: BusinessPlanWrite,
    access: UpdateAccess,
    use_case: SubmitBusinessPlanDep,
    response: Response,
) -> BusinessPlanRead:
    """The startup's project before an application: needs `edit_financials`. A new plan — 201,
    a revised one — 200; the bank's assessment of an older revision stays until it is run
    again (`POST /organizations/{id}/project-assessment`)."""
    plan, created = await use_case.execute(access, organization_id, data.to_dto())
    if created:
        response.status_code = status.HTTP_201_CREATED
    return BusinessPlanRead.model_validate(plan)
