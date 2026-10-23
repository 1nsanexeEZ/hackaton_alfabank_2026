from uuid import UUID

from fastapi import APIRouter

from src.modules.clients.presentation.dependencies import (
    GetOrganizationDep,
    ListOrganizationsDep,
    ReadAccess,
    UpdateAccess,
    VerifyOrganizationDep,
)
from src.modules.clients.presentation.schemas.organizations import (
    OrganizationRead,
    OrganizationSummaryRead,
    VerificationResultRead,
)

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.get("", response_model=list[OrganizationSummaryRead])
async def list_organizations(
    access: ReadAccess, use_case: ListOrganizationsDep
) -> list[OrganizationSummaryRead]:
    """My companies with my role and rights; the bank sees every company."""
    return [OrganizationSummaryRead.model_validate(org) for org in await use_case.execute(access)]


@router.get("/{organization_id}", response_model=OrganizationRead)
async def get_organization(
    organization_id: UUID, access: ReadAccess, use_case: GetOrganizationDep
) -> OrganizationRead:
    return OrganizationRead.model_validate(await use_case.execute(access, organization_id))


@router.post("/{organization_id}/verification", response_model=VerificationResultRead)
async def verify_organization(
    organization_id: UUID, access: UpdateAccess, use_case: VerifyOrganizationDep
) -> VerificationResultRead:
    """Check against ЕГРЮЛ/ЕГРИП, past the cache. Name, address, KPP, OKVED
    and the registry status follow the registry (`updated_fields`); a
    different head is a discrepancy and the check ends in `mismatch`. A
    member of the company or bank staff; unknown INN — 422
    `registry_not_found`; the registry did not answer — 503, nothing changes."""
    return VerificationResultRead.model_validate(await use_case.execute(access, organization_id))
