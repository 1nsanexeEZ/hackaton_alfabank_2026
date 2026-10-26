from uuid import UUID

from fastapi import APIRouter, status

from src.modules.clients.presentation.dependencies import (
    AddMemberDep,
    ChangeMemberRoleDep,
    GrantPowerOfAttorneyDep,
    ListMembersDep,
    ReadAccess,
    RemoveMemberDep,
    RevokePowerOfAttorneyDep,
    UpdateAccess,
)
from src.modules.clients.presentation.schemas.members import (
    MemberCreate,
    MemberRead,
    MemberUpdate,
    PowerOfAttorneyCreate,
)

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.get("/{organization_id}/members", response_model=list[MemberRead])
async def list_members(
    organization_id: UUID, access: ReadAccess, use_case: ListMembersDep
) -> list[MemberRead]:
    members = await use_case.execute(access, organization_id)
    return [MemberRead.model_validate(member) for member in members]


@router.post(
    "/{organization_id}/members",
    response_model=MemberRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_member(
    organization_id: UUID, data: MemberCreate, access: UpdateAccess, use_case: AddMemberDep
) -> MemberRead:
    """An existing account by email or phone; unknown login — 422."""
    member = await use_case.execute(access, organization_id, data.login, data.role)
    return MemberRead.model_validate(member)


@router.patch("/{organization_id}/members/{account_id}", response_model=MemberRead)
async def change_member_role(
    organization_id: UUID,
    account_id: UUID,
    data: MemberUpdate,
    access: UpdateAccess,
    use_case: ChangeMemberRoleDep,
) -> MemberRead:
    member = await use_case.execute(access, organization_id, account_id, data.role)
    return MemberRead.model_validate(member)


@router.delete("/{organization_id}/members/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    organization_id: UUID, account_id: UUID, access: UpdateAccess, use_case: RemoveMemberDep
) -> None:
    await use_case.execute(access, organization_id, account_id)


@router.post("/{organization_id}/members/{account_id}/poa", response_model=MemberRead)
async def grant_power_of_attorney(
    organization_id: UUID,
    account_id: UUID,
    data: PowerOfAttorneyCreate,
    access: UpdateAccess,
    use_case: GrantPowerOfAttorneyDep,
) -> MemberRead:
    """Issued by the head confirmed by the registry. The number: letters and digits separated
    by spaces, dots, slashes or hyphens, with a digit, up to 32 characters, "№" is dropped —
    otherwise 422 `invalid_format`; another member's number — 409 `number_taken`. One at a
    time: a current or not yet started one — 409 `power_of_attorney_exists` (revoke it first),
    an expired one is replaced."""
    member = await use_case.execute(access, organization_id, account_id, data.to_dto())
    return MemberRead.model_validate(member)


@router.delete("/{organization_id}/members/{account_id}/poa", response_model=MemberRead)
async def revoke_power_of_attorney(
    organization_id: UUID,
    account_id: UUID,
    access: UpdateAccess,
    use_case: RevokePowerOfAttorneyDep,
) -> MemberRead:
    """Revoked by the head confirmed by the registry: the rights it gave (submitting
    applications, signing, the pre-approved offers) end at once. The member without one —
    404 `power_of_attorney_not_found`."""
    member = await use_case.execute(access, organization_id, account_id)
    return MemberRead.model_validate(member)
