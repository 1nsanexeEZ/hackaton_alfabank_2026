from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from src.modules.bff.presentation.dependencies import (
    ApplicationCardDep,
    CanReadApplications,
    CanReadOrganizations,
    CanReadProducts,
    DashboardDep,
    ListApplicationsDep,
    PersonalScheduleDep,
    RecommendProductsDep,
)
from src.modules.bff.presentation.schemas.client import (
    ApplicationList,
    ClientApplicationCard,
    Dashboard,
    PersonalCalculateBody,
    PersonalSchedule,
    Recommendations,
)
from src.modules.products.facade import Purpose

router = APIRouter(prefix="/bff", tags=["bff"])


@router.get("/dashboard", response_model=Dashboard)
async def dashboard(
    access: CanReadOrganizations,
    use_case: DashboardDep,
    organization_id: UUID | None = None,
) -> Dashboard:
    """Main screen of the client; without organization_id — the first company."""
    return Dashboard.model_validate(await use_case.execute(access, organization_id))


@router.get("/applications", response_model=ApplicationList)
async def list_applications(
    access: CanReadApplications,
    use_case: ListApplicationsDep,
    organization_id: UUID,
    status: Annotated[
        str | None, Query(description="Backend status: draft, in_review, offer_ready...")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ApplicationList:
    return ApplicationList.model_validate(
        await use_case.execute(access, organization_id, status, limit, offset)
    )


@router.get("/applications/{application_id}", response_model=ClientApplicationCard)
async def get_application(
    application_id: UUID, access: CanReadApplications, use_case: ApplicationCardDep
) -> ClientApplicationCard:
    """The card and its status come from applications, not from the projection."""
    return ClientApplicationCard.model_validate(await use_case.execute(access, application_id))


@router.get("/products/recommend", response_model=Recommendations)
async def recommend_products(
    access: CanReadProducts,
    use_case: RecommendProductsDep,
    purpose: Purpose,
    amount: Annotated[Decimal, Query(gt=0, max_digits=15, decimal_places=2)],
    term_months: Annotated[int, Query(ge=1, le=360)],
    organization_id: UUID | None = None,
) -> Recommendations:
    """With organization_id: eligibility of the company and pre-approved amounts."""
    return Recommendations.model_validate(
        await use_case.execute(access, organization_id, purpose, amount, term_months)
    )


@router.post("/products/{code}/calculate", response_model=PersonalSchedule)
async def calculate_for_organization(
    code: str,
    data: PersonalCalculateBody,
    access: CanReadProducts,
    use_case: PersonalScheduleDep,
    organization_id: UUID,
) -> PersonalSchedule:
    """Schedule at the pre-approved rate and how the request fits the pre-approved
    terms. Above them is a reason and a suggestion, not an error."""
    return PersonalSchedule.model_validate(
        await use_case.execute(access, organization_id, code, data.to_dto())
    )
