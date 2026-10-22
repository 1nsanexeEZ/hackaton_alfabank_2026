"""Pre-approved offers of a company for the cabinet dashboard; the rest of decision goes
through bff."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from src.core.access.dependencies import require_permissions
from src.core.access.permissions import Permissions
from src.core.facades import use_facade
from src.core.schemas.jwt_dto import OpenSubTokenDTO
from src.modules.clients.facade import ClientsFacade
from src.modules.decision.api.dependencies import ensure_can_view
from src.modules.decision.api.schemas import PreApprovedOfferRead
from src.modules.decision.facade import DecisionFacade

router = APIRouter(prefix="/organizations", tags=["decision"])

OrganizationsReader = Annotated[
    OpenSubTokenDTO, Depends(require_permissions(Permissions.ORGANIZATIONS_READ))
]
Clients = Annotated[ClientsFacade, Depends(use_facade(ClientsFacade))]
Decisions = Annotated[DecisionFacade, Depends(use_facade(DecisionFacade))]


@router.get("/{organization_id}/pre-approved-offers", response_model=list[PreApprovedOfferRead])
async def list_pre_approved_offers(
    organization_id: UUID, token: OrganizationsReader, clients: Clients, decisions: Decisions
) -> list[PreApprovedOfferRead]:
    """Valid offers, the largest first; an empty list when nothing is pre-approved."""
    await ensure_can_view(token, organization_id, clients)
    return [PreApprovedOfferRead.of(o) for o in await decisions.get_pre_approved(organization_id)]
