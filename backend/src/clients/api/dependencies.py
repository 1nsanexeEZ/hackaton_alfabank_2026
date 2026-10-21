from typing import Annotated

from fastapi import Depends, Request

from src.clients.application.events import PRODUCER
from src.clients.application.services import OrganizationService
from src.clients.infrastructure.repositories import (
    SqlAlchemyFinancialReportRepository,
    SqlAlchemyOrganizationRepository,
)
from src.core.access.access_context import AccessContext
from src.core.access.dependencies import get_access_context_for
from src.core.access.permissions import Permissions
from src.core.facades import use_facade
from src.core.infrastructure.database.session import DbSession
from src.core.messaging.outbox import SqlAlchemyOutboxWriter
from src.core.uow import SqlAlchemyUnitOfWork
from src.identity.facade import IdentityFacade


def get_organization_service(request: Request, session: DbSession) -> OrganizationService:
    clock = request.app.state.clock
    return OrganizationService(
        uow=SqlAlchemyUnitOfWork(session),
        organizations=SqlAlchemyOrganizationRepository(session),
        reports=SqlAlchemyFinancialReportRepository(session),
        outbox=SqlAlchemyOutboxWriter(session, PRODUCER, clock),
        clock=clock,
    )


ServiceDep = Annotated[OrganizationService, Depends(get_organization_service)]
IdentityDep = Annotated[IdentityFacade, Depends(use_facade(IdentityFacade))]
ReadAccess = Annotated[
    AccessContext, Depends(get_access_context_for(Permissions.ORGANIZATIONS_READ))
]
UpdateAccess = Annotated[
    AccessContext, Depends(get_access_context_for(Permissions.ORGANIZATIONS_UPDATE))
]
