from typing import Annotated

from fastapi import APIRouter, Depends

from src.core.access.dependencies import CurrentToken, require_permissions
from src.core.access.permissions import Permissions
from src.core.schemas.jwt_dto import OpenSubTokenDTO
from src.modules.identity.dependencies import AccountServiceDep
from src.modules.identity.models import Account
from src.modules.identity.schemas import AccountRead, MeRead, ProfileUpdate

router = APIRouter(prefix="/me", tags=["me"])


def _me(account: Account, token: OpenSubTokenDTO) -> MeRead:
    # Rights are taken from the token: that's what every module will enforce
    # until it expires, even if the role was edited in the meantime.
    return MeRead(
        **AccountRead.model_validate(account).model_dump(),
        permissions=token.permissions,
        policies=token.policies,
    )


@router.get("", response_model=MeRead)
async def get_me(token: CurrentToken, service: AccountServiceDep) -> MeRead:
    return _me(await service.me(token.subject), token)


@router.patch("/profile", response_model=MeRead)
async def update_my_profile(
    data: ProfileUpdate,
    token: Annotated[OpenSubTokenDTO, Depends(require_permissions(Permissions.PROFILE_UPDATE))],
    service: AccountServiceDep,
) -> MeRead:
    return _me(await service.update_my_profile(token.subject, data), token)
