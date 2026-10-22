from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field

from src.modules.bff.api.dependencies import (
    CanReadApplications,
    CanReadOrganizations,
    CanReadProducts,
    ClientScreensDep,
)
from src.modules.bff.application import views
from src.modules.products.facade import Purpose, Repayment

router = APIRouter(prefix="/bff", tags=["bff"])


class PersonalCalculateBody(BaseModel):
    """As for `POST /products/{code}/calculate`, but without the rate: the bank sets it."""

    model_config = ConfigDict(extra="forbid")

    amount: Annotated[Decimal, Field(gt=0, max_digits=18, decimal_places=2)]
    term_months: Annotated[int, Field(ge=1, le=360)]
    # The default schedule of the product when omitted.
    repayment: Repayment | None = None


@router.get("/dashboard", response_model=views.Dashboard)
async def dashboard(
    access: CanReadOrganizations,
    screens: ClientScreensDep,
    organization_id: UUID | None = None,
) -> views.Dashboard:
    """Main screen of the client; without organization_id — the first company."""
    return await screens.dashboard(access.user_id, access.organization_ids, organization_id)


@router.get("/applications", response_model=views.ApplicationList)
async def list_applications(
    access: CanReadApplications,
    screens: ClientScreensDep,
    organization_id: UUID,
    status: Annotated[
        str | None, Query(description="Backend status: draft, in_review, offer_ready...")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> views.ApplicationList:
    return await screens.applications(
        access.user_id, access.organization_ids, organization_id, status, limit, offset
    )


@router.get("/applications/{application_id}", response_model=views.ClientApplicationCard)
async def get_application(
    application_id: UUID, access: CanReadApplications, screens: ClientScreensDep
) -> views.ClientApplicationCard:
    """The card and its status come from applications, not from the projection."""
    return await screens.application(access.user_id, access.organization_ids, application_id)


@router.get("/products/recommend", response_model=views.Recommendations)
async def recommend_products(
    access: CanReadProducts,
    screens: ClientScreensDep,
    purpose: Purpose,
    amount: Annotated[Decimal, Query(gt=0, max_digits=15, decimal_places=2)],
    term_months: Annotated[int, Query(ge=1, le=360)],
    organization_id: UUID | None = None,
) -> views.Recommendations:
    """With organization_id: eligibility of the company and pre-approved amounts."""
    return await screens.recommendations(
        access.user_id, access.organization_ids, organization_id, purpose, amount, term_months
    )


@router.post("/products/{code}/calculate", response_model=views.PersonalSchedule)
async def calculate_for_organization(
    code: str,
    data: PersonalCalculateBody,
    access: CanReadProducts,
    screens: ClientScreensDep,
    organization_id: UUID,
) -> views.PersonalSchedule:
    """Schedule at the pre-approved rate and how the request fits the pre-approved
    terms. Above them is a reason and a suggestion, not an error."""
    return await screens.personal_schedule(
        access.user_id,
        access.organization_ids,
        organization_id,
        code,
        data.amount,
        data.term_months,
        data.repayment,
    )
