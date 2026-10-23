from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from src.core.access.access_context import AccessContext
from src.core.access.dependencies import get_access_context_for, require_permissions
from src.core.access.permissions import Permissions
from src.modules.identity.presentation.dependencies import (
    CreateRoleDep,
    DeleteRoleDep,
    GetRoleDep,
    ListRolesDep,
    UpdateRoleDep,
)
from src.modules.identity.presentation.schemas.roles import RoleCreate, RoleRead, RoleUpdate

router = APIRouter(prefix="/roles", tags=["roles"])


@router.get("", response_model=list[RoleRead])
async def list_roles(
    access: Annotated[AccessContext, Depends(get_access_context_for(Permissions.ROLES_READ))],
    use_case: ListRolesDep,
) -> list[RoleRead]:
    return [RoleRead.model_validate(role) for role in await use_case.execute(access)]


@router.get("/{role_id}", response_model=RoleRead)
async def get_role(
    role_id: UUID,
    access: Annotated[AccessContext, Depends(get_access_context_for(Permissions.ROLES_READ))],
    use_case: GetRoleDep,
) -> RoleRead:
    return RoleRead.model_validate(await use_case.execute(access, role_id))


@router.post(
    "",
    response_model=RoleRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permissions(Permissions.ROLES_CREATE))],
)
async def create_role(data: RoleCreate, use_case: CreateRoleDep) -> RoleRead:
    """`policies` maps a permission to the row-level policies applied with it,
    e.g. `{"requests.read": ["own_only", "not_deleted"]}`. Every key must be
    listed in `permissions`."""
    return RoleRead.model_validate(await use_case.execute(data.to_dto()))


@router.patch("/{role_id}", response_model=RoleRead)
async def update_role(
    role_id: UUID,
    data: RoleUpdate,
    access: Annotated[AccessContext, Depends(get_access_context_for(Permissions.ROLES_UPDATE))],
    use_case: UpdateRoleDep,
) -> RoleRead:
    """Accounts get the new rights with their next token."""
    return RoleRead.model_validate(await use_case.execute(access, role_id, data.to_dto()))


@router.delete("/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role(
    role_id: UUID,
    access: Annotated[AccessContext, Depends(get_access_context_for(Permissions.ROLES_DELETE))],
    use_case: DeleteRoleDep,
) -> None:
    """409 while any account (deleted ones included) still has this role."""
    await use_case.execute(access, role_id)
