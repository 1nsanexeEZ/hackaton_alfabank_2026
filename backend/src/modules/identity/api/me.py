from typing import Annotated

from fastapi import APIRouter, Depends, Request, status

from src.core.access.dependencies import CurrentToken, require_permissions
from src.core.access.permissions import Permissions
from src.core.schemas.jwt_dto import OpenSubTokenDTO
from src.modules.identity.dependencies import AccountServiceDep, ConsentServiceDep
from src.modules.identity.facade import ConsentType
from src.modules.identity.models import Account
from src.modules.identity.schemas import (
    AccountRead,
    ConsentGive,
    ConsentRead,
    MeRead,
    ProfileUpdate,
)

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


@router.get("/consents", response_model=list[ConsentRead])
async def list_my_consents(token: CurrentToken, service: ConsentServiceDep) -> list[ConsentRead]:
    """Personal consents in force and the history, newest first."""
    return await service.list(token.subject)


@router.post("/consents", response_model=list[ConsentRead], status_code=status.HTTP_201_CREATED)
async def give_my_consents(
    data: ConsentGive, request: Request, token: CurrentToken, service: ConsentServiceDep
) -> list[ConsentRead]:
    """Each type is a new consent row; the request's IP and User-Agent are kept with it."""
    return await service.give(
        token.subject,
        data.types,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )


@router.delete("/consents/{type}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_my_consent(
    type: ConsentType, token: CurrentToken, service: ConsentServiceDep
) -> None:
    """Revoking an absent or already revoked consent is also 204."""
    await service.revoke(token.subject, type)
