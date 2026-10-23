from typing import Annotated

from fastapi import APIRouter, Depends, Request, status

from src.core.access.dependencies import CurrentToken, require_permissions
from src.core.access.permissions import Permissions
from src.core.schemas.jwt_dto import OpenSubTokenDTO
from src.modules.identity.application.dto.consents import GiveConsentsDTO
from src.modules.identity.domain.enums import ConsentType
from src.modules.identity.presentation.dependencies import (
    GetMeDep,
    GiveConsentsDep,
    ListMyConsentsDep,
    RevokeConsentDep,
    UpdateMyProfileDep,
)
from src.modules.identity.presentation.schemas.accounts import ProfileUpdate
from src.modules.identity.presentation.schemas.consents import ConsentGive, ConsentRead
from src.modules.identity.presentation.schemas.me import MeRead

router = APIRouter(prefix="/me", tags=["me"])


@router.get("", response_model=MeRead)
async def get_me(token: CurrentToken, use_case: GetMeDep) -> MeRead:
    return MeRead.build(await use_case.execute(token.subject), token)


@router.patch("/profile", response_model=MeRead)
async def update_my_profile(
    data: ProfileUpdate,
    token: Annotated[OpenSubTokenDTO, Depends(require_permissions(Permissions.PROFILE_UPDATE))],
    use_case: UpdateMyProfileDep,
) -> MeRead:
    return MeRead.build(await use_case.execute(token.subject, data.to_dto()), token)


@router.get("/consents", response_model=list[ConsentRead])
async def list_my_consents(token: CurrentToken, use_case: ListMyConsentsDep) -> list[ConsentRead]:
    """Personal consents in force and the history, newest first."""
    return [ConsentRead.model_validate(c) for c in await use_case.execute(token.subject)]


@router.post("/consents", response_model=list[ConsentRead], status_code=status.HTTP_201_CREATED)
async def give_my_consents(
    data: ConsentGive, request: Request, token: CurrentToken, use_case: GiveConsentsDep
) -> list[ConsentRead]:
    """Each type is a new consent row; the request's IP and User-Agent are kept with it."""
    given = await use_case.execute(
        token.subject,
        GiveConsentsDTO(
            types=data.types,
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        ),
    )
    return [ConsentRead.model_validate(c) for c in given]


@router.delete("/consents/{type}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_my_consent(
    type: ConsentType, token: CurrentToken, use_case: RevokeConsentDep
) -> None:
    """Revoking an absent or already revoked consent is also 204."""
    await use_case.execute(token.subject, type)
