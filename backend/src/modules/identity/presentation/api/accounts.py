from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from src.core.access.access_context import AccessContext
from src.core.access.dependencies import get_access_context_for, require_permissions
from src.core.access.permissions import Permissions
from src.core.http.pagination import TOTAL_HEADER
from src.modules.identity.presentation.dependencies import (
    CreateAccountDep,
    DeleteAccountDep,
    GetAccountDep,
    ListAccountsDep,
    UpdateAccountDep,
)
from src.modules.identity.presentation.schemas.accounts import (
    AccountCreate,
    AccountRead,
    AccountUpdate,
)

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.get("", response_model=list[AccountRead])
async def list_accounts(
    response: Response,
    access: Annotated[AccessContext, Depends(get_access_context_for(Permissions.ACCOUNTS_READ))],
    use_case: ListAccountsDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AccountRead]:
    """The total by the same filter is in the `X-Total-Count` header."""
    accounts, total = await use_case.execute(access, limit, offset)
    response.headers[TOTAL_HEADER] = str(total)
    return [AccountRead.model_validate(account) for account in accounts]


@router.get("/{account_id}", response_model=AccountRead)
async def get_account(
    account_id: UUID,
    access: Annotated[AccessContext, Depends(get_access_context_for(Permissions.ACCOUNTS_READ))],
    use_case: GetAccountDep,
) -> AccountRead:
    return AccountRead.model_validate(await use_case.execute(access, account_id))


@router.post(
    "",
    response_model=AccountRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permissions(Permissions.ACCOUNTS_CREATE))],
)
async def create_account(data: AccountCreate, use_case: CreateAccountDep) -> AccountRead:
    return AccountRead.model_validate(await use_case.execute(data.to_dto()))


@router.patch("/{account_id}", response_model=AccountRead)
async def update_account(
    account_id: UUID,
    data: AccountUpdate,
    access: Annotated[AccessContext, Depends(get_access_context_for(Permissions.ACCOUNTS_UPDATE))],
    use_case: UpdateAccountDep,
) -> AccountRead:
    return AccountRead.model_validate(await use_case.execute(access, account_id, data.to_dto()))


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    account_id: UUID,
    access: Annotated[AccessContext, Depends(get_access_context_for(Permissions.ACCOUNTS_DELETE))],
    use_case: DeleteAccountDep,
) -> None:
    """Soft delete: the account can't log in and disappears for roles with `not_deleted`."""
    await use_case.execute(access, account_id)
