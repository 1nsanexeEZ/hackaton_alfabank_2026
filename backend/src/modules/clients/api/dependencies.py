from typing import Annotated

from fastapi import Depends, Request

from src.core.access.access_context import AccessContext
from src.core.access.dependencies import get_access_context_for
from src.core.access.permissions import Permissions
from src.core.facades import use_facade
from src.core.infrastructure.database.session import DbSession
from src.core.messaging.outbox import SqlAlchemyOutboxWriter
from src.core.uow import SqlAlchemyUnitOfWork
from src.modules.clients.application.events import PRODUCER
from src.modules.clients.application.services import OrganizationService
from src.modules.clients.application.verification import VerifyOrganizationUseCase
from src.modules.clients.infrastructure.registry import EnrichmentRegistryLookup
from src.modules.clients.infrastructure.repositories import (
    SqlAlchemyFinancialReportRepository,
    SqlAlchemyOrganizationRepository,
)
from src.modules.enrichment.facade import EnrichmentFacade
from src.modules.identity.facade import IdentityFacade

IdentityDep = Annotated[IdentityFacade, Depends(use_facade(IdentityFacade))]
EnrichmentDep = Annotated[EnrichmentFacade, Depends(use_facade(EnrichmentFacade))]


def get_organization_service(request: Request, session: DbSession) -> OrganizationService:
    clock = request.app.state.clock
    return OrganizationService(
        uow=SqlAlchemyUnitOfWork(session),
        organizations=SqlAlchemyOrganizationRepository(session),
        reports=SqlAlchemyFinancialReportRepository(session),
        outbox=SqlAlchemyOutboxWriter(session, PRODUCER, clock),
        clock=clock,
    )


def get_verify_use_case(
    request: Request, session: DbSession, identity: IdentityDep, enrichment: EnrichmentDep
) -> VerifyOrganizationUseCase:
    clock = request.app.state.clock
    return VerifyOrganizationUseCase(
        uow=SqlAlchemyUnitOfWork(session),
        organizations=SqlAlchemyOrganizationRepository(session),
        outbox=SqlAlchemyOutboxWriter(session, PRODUCER, clock),
        clock=clock,
        registry=EnrichmentRegistryLookup(enrichment),
        identity=identity,
    )


ServiceDep = Annotated[OrganizationService, Depends(get_organization_service)]
VerifyDep = Annotated[VerifyOrganizationUseCase, Depends(get_verify_use_case)]
ReadAccess = Annotated[
    AccessContext, Depends(get_access_context_for(Permissions.ORGANIZATIONS_READ))
]
UpdateAccess = Annotated[
    AccessContext, Depends(get_access_context_for(Permissions.ORGANIZATIONS_UPDATE))
]
