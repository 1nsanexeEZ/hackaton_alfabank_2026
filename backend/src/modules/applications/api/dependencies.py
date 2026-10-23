from typing import Annotated

from fastapi import Depends, Request

from src.core.access.access_context import AccessContext
from src.core.access.dependencies import get_access_context_for
from src.core.access.permissions import Permissions
from src.core.infrastructure.database.session import DbSession
from src.core.messaging.outbox import SqlAlchemyOutboxWriter
from src.modules.applications.application.service import ApplicationService
from src.modules.applications.infrastructure.repository import SqlAlchemyApplicationRepository
from src.modules.clients.facade import ClientsFacade
from src.modules.identity.facade import IdentityFacade
from src.modules.products.facade import ProductsFacade


def get_service(request: Request, session: DbSession) -> ApplicationService:
    state = request.app.state
    return ApplicationService(
        session=session,
        repository=SqlAlchemyApplicationRepository(session),
        outbox=SqlAlchemyOutboxWriter(session, "applications", state.clock),
        storage=state.document_storage,
        edo=state.edo_client,
        clients=state.facades.get(ClientsFacade, session),
        products=state.facades.get(ProductsFacade, session),
        identity=state.facades.get(IdentityFacade, session),
        clock=state.clock,
    )


Service = Annotated[ApplicationService, Depends(get_service)]
CanRead = Annotated[AccessContext, Depends(get_access_context_for(Permissions.REQUESTS_READ))]
CanCreate = Annotated[AccessContext, Depends(get_access_context_for(Permissions.REQUESTS_CREATE))]
CanUpdate = Annotated[AccessContext, Depends(get_access_context_for(Permissions.REQUESTS_UPDATE))]


def client_ip(request: Request) -> str | None:
    # nginx puts the real address here; the backend itself is not exposed.
    return request.headers.get("x-real-ip") or (request.client.host if request.client else None)
