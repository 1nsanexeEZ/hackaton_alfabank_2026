"""Pre-approved offers of a company for the cabinet dashboard, the startup founder's prescreen
and the startup's project assessment; the rest of decision goes through bff."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status

from src.core.access.dependencies import require_permissions
from src.core.access.permissions import Permissions
from src.core.exceptions.exceptions import NotFoundError
from src.core.facades import use_facade
from src.core.infrastructure.database.session import DbSession
from src.core.messaging.outbox import SqlAlchemyOutboxWriter
from src.core.schemas.jwt_dto import OpenSubTokenDTO
from src.modules.clients.facade import ClientsFacade, OrgPermission
from src.modules.decision.api.dependencies import (
    ActivePolicyDep,
    ensure_can_view,
    sees_every_organization,
)
from src.modules.decision.api.schemas import (
    FounderPrescreenRead,
    PreApprovedOfferRead,
    ProjectAssessmentRead,
)
from src.modules.decision.application.founder_prescreen import FounderPrescreenUseCase
from src.modules.decision.application.project_assessment import AssessProjectUseCase
from src.modules.decision.facade import DecisionFacade
from src.modules.decision.infrastructure.mappers import prescreen_dto, project_dto
from src.modules.decision.infrastructure.repository import (
    SqlAlchemyFounderPrescreenRepository,
    SqlAlchemyPreApprovedOfferRepository,
    SqlAlchemyProjectAssessmentRepository,
)
from src.modules.enrichment.facade import EnrichmentFacade
from src.modules.identity.facade import IdentityFacade
from src.modules.products.facade import ProductsFacade
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
Products = Annotated[ProductsFacade, Depends(use_facade(ProductsFacade))]


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


@router.post(
    "/{organization_id}/project-assessment",
    response_model=ProjectAssessmentRead,
    status_code=status.HTTP_201_CREATED,
)
async def run_project_assessment(
    organization_id: UUID,
    request: Request,
    token: OrganizationsReader,
    session: DbSession,
    clients: Clients,
    products: Products,
    scoring: Scoring,
    policy: ActivePolicyDep,
) -> ProjectAssessmentRead:
    """The startup's project by its business plan from the cabinet: passed — a pre-approved
    STARTUP offer (`basis = project`) up to `max_amount`, also in `pre-approved-offers`.
    422 `business_plan_required` — no business plan; 422 `product_not_eligible` — no startup
    product fits the company."""
    if not sees_every_organization(token):
        await clients.ensure_can(token.subject, organization_id, OrgPermission.SUBMIT_APPLICATION)
    clock = request.app.state.clock
    assessment = await AssessProjectUseCase(
        SqlAlchemyProjectAssessmentRepository(session),
        SqlAlchemyPreApprovedOfferRepository(session),
        SqlAlchemyFounderPrescreenRepository(session),
        policy,
        clients,
        products,
        scoring,
        clock,
    ).run(organization_id, outbox=SqlAlchemyOutboxWriter(session, "decision", clock))
    await session.commit()
    return ProjectAssessmentRead.of(project_dto(assessment, clock.now()))


@router.get("/{organization_id}/project-assessment", response_model=ProjectAssessmentRead)
async def get_project_assessment(
    organization_id: UUID, token: OrganizationsReader, clients: Clients, decisions: Decisions
) -> ProjectAssessmentRead:
    """The latest assessment; 404 — not run yet."""
    await ensure_can_view(token, organization_id, clients)
    assessment = await decisions.get_project_assessment(organization_id)
    if assessment is None:
        raise NotFoundError("Project assessment not found")
    return ProjectAssessmentRead.of(assessment)
