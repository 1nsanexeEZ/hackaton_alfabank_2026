from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from src.core.access.access_context import AccessContext
from src.core.access.dependencies import get_access_context_for, require_permissions
from src.core.access.permissions import Permissions
from src.identity.dependencies import AccountServiceDep
from src.identity.schemas import AccountCreate, AccountRead, AccountUpdate

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.get("", response_model=list[AccountRead])
async def list_accounts(
    access: Annotated[AccessContext, Depends(get_access_context_for(Permissions.ACCOUNTS_READ))],
    service: AccountServiceDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AccountRead]:
    accounts = await service.list(access, limit, offset)
    return [AccountRead.model_validate(account) for account in accounts]


@router.get("/{account_id}", response_model=AccountRead)
async def get_account(
    account_id: UUID,
    access: Annotated[AccessContext, Depends(get_access_context_for(Permissions.ACCOUNTS_READ))],
    service: AccountServiceDep,
) -> AccountRead:
    return AccountRead.model_validate(await service.get(access, account_id))


@router.post(
    "",
    response_model=AccountRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permissions(Permissions.ACCOUNTS_CREATE))],
)
async def create_account(data: AccountCreate, service: AccountServiceDep) -> AccountRead:
    return AccountRead.model_validate(await service.create(data))


@router.patch("/{account_id}", response_model=AccountRead)
async def update_account(
    account_id: UUID,
    data: AccountUpdate,
    access: Annotated[AccessContext, Depends(get_access_context_for(Permissions.ACCOUNTS_UPDATE))],
    service: AccountServiceDep,
) -> AccountRead:
    return AccountRead.model_validate(await service.update(access, account_id, data))


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    account_id: UUID,
    access: Annotated[AccessContext, Depends(get_access_context_for(Permissions.ACCOUNTS_DELETE))],
    service: AccountServiceDep,
) -> None:
    """Soft delete: the account can't log in and disappears for roles with `not_deleted`."""
    await service.delete(access, account_id)
