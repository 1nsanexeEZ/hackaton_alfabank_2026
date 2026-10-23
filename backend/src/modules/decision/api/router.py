"""Pre-approved offers of a company for the cabinet dashboard and the startup founder's
prescreen; the rest of decision goes through bff."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status

from src.core.access.dependencies import require_permissions
from src.core.access.permissions import Permissions
from src.core.exceptions.exceptions import NotFoundError
from src.core.facades import use_facade
from src.core.infrastructure.database.session import DbSession
from src.core.schemas.jwt_dto import OpenSubTokenDTO
from src.modules.clients.facade import ClientsFacade, OrgPermission
from src.modules.decision.api.dependencies import ensure_can_view, sees_every_organization
from src.modules.decision.api.schemas import FounderPrescreenRead, PreApprovedOfferRead
from src.modules.decision.application.founder_prescreen import FounderPrescreenUseCase
from src.modules.decision.facade import DecisionFacade
from src.modules.decision.infrastructure.mappers import prescreen_dto
from src.modules.decision.infrastructure.repository import SqlAlchemyFounderPrescreenRepository
from src.modules.enrichment.facade import EnrichmentFacade
from src.modules.identity.facade import IdentityFacade
from src.modules.scoring.facade import ScoringFacade

router = APIRouter(prefix="/organizations", tags=["decision"])

OrganizationsReader = Annotated[
    OpenSubTokenDTO, Depends(require_permissions(Permissions.ORGANIZATIONS_READ))
]
Clients = Annotated[ClientsFacade, Depends(use_facade(ClientsFacade))]
Decisions = Annotated[DecisionFacade, Depends(use_facade(DecisionFacade))]
Identity = Annotated[IdentityFacade, Depends(use_facade(IdentityFacade))]
Enrichment = Annotated[EnrichmentFacade, Depends(use_facade(EnrichmentFacade))]
Scoring = Annotated[ScoringFacade, Depends(use_facade(ScoringFacade))]


@router.get("/{organization_id}/pre-approved-offers", response_model=list[PreApprovedOfferRead])
async def list_pre_approved_offers(
    organization_id: UUID, token: OrganizationsReader, clients: Clients, decisions: Decisions
) -> list[PreApprovedOfferRead]:
    """Valid offers, the largest first; an empty list when nothing is pre-approved."""
    await ensure_can_view(token, organization_id, clients)
    return [PreApprovedOfferRead.of(o) for o in await decisions.get_pre_approved(organization_id)]


@router.post(
    "/{organization_id}/founder-prescreen",
    response_model=FounderPrescreenRead,
    status_code=status.HTTP_201_CREATED,
)
async def run_founder_prescreen(
    organization_id: UUID,
    request: Request,
    token: OrganizationsReader,
    session: DbSession,
    clients: Clients,
    identity: Identity,
    enrichment: Enrichment,
    scoring: Scoring,
) -> FounderPrescreenRead:
    """The founder's own credit history before a STARTUP application. 422 `founder_not_found`
    — no member matches the head by the registry; 422 `consent_required` — the founder has not
    given `credit_bureau_personal`."""
    if not sees_every_organization(token):
        await clients.ensure_can(token.subject, organization_id, OrgPermission.SUBMIT_APPLICATION)
    clock = request.app.state.clock
    prescreen = await FounderPrescreenUseCase(
        SqlAlchemyFounderPrescreenRepository(session), clients, identity, enrichment, scoring, clock
    ).run(organization_id)
    await session.commit()
    return FounderPrescreenRead.of(prescreen_dto(prescreen, clock.now()))


@router.get("/{organization_id}/founder-prescreen", response_model=FounderPrescreenRead)
async def get_founder_prescreen(
    organization_id: UUID, token: OrganizationsReader, clients: Clients, decisions: Decisions
) -> FounderPrescreenRead:
    """The latest prescreen; 404 — not run yet."""
    await ensure_can_view(token, organization_id, clients)
    prescreen = await decisions.get_founder_prescreen(organization_id)
    if prescreen is None:
        raise NotFoundError("Prescreen not found")
    return FounderPrescreenRead.of(prescreen)
