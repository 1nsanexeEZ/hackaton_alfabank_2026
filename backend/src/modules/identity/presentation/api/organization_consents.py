from uuid import UUID

from fastapi import APIRouter, Request, status

from src.core.access.dependencies import CurrentToken
from src.modules.identity.application.dto.consents import GiveConsentsDTO
from src.modules.identity.domain.enums import CompanyConsentType
from src.modules.identity.presentation.dependencies import (
    GiveOrganizationConsentsDep,
    ListOrganizationConsentsDep,
    RevokeOrganizationConsentDep,
)
from src.modules.identity.presentation.schemas.consents import (
    OrganizationConsentGive,
    OrganizationConsentRead,
)

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.get("/{organization_id}/consents", response_model=list[OrganizationConsentRead])
async def list_organization_consents(
    organization_id: UUID, token: CurrentToken, use_case: ListOrganizationConsentsDep
) -> list[OrganizationConsentRead]:
    """Company consents in force and the history, newest first. Needs `view` in the company."""
    consents = await use_case.execute(token.subject, organization_id)
    return [OrganizationConsentRead.model_validate(c) for c in consents]


@router.post(
    "/{organization_id}/consents",
    response_model=list[OrganizationConsentRead],
    status_code=status.HTTP_201_CREATED,
)
async def give_organization_consents(
    organization_id: UUID,
    data: OrganizationConsentGive,
    request: Request,
    token: CurrentToken,
    use_case: GiveOrganizationConsentsDep,
) -> list[OrganizationConsentRead]:
    """A representative with `submit_application` gives the consent for the company before
    an application; drafts and submissions take it from here."""
    given = await use_case.execute(
        token.subject,
        organization_id,
        GiveConsentsDTO(
            types=data.types,
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        ),
    )
    return [OrganizationConsentRead.model_validate(c) for c in given]


@router.delete("/{organization_id}/consents/{type}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_organization_consent(
    organization_id: UUID,
    type: CompanyConsentType,
    token: CurrentToken,
    use_case: RevokeOrganizationConsentDep,
) -> None:
    """Any representative with `submit_application` may revoke; an absent or already
    revoked consent is also 204. Applications already submitted keep their consents."""
    await use_case.execute(token.subject, organization_id, type)
