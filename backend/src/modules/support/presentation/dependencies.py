"""Use cases for the routers: adapters are picked here, use cases see only interfaces."""

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request

from src.core.access.access_context import AccessContext
from src.core.access.dependencies import get_access_context_for
from src.core.access.permissions import Permissions
from src.core.domain.clock import Clock
from src.core.facades import use_facade
from src.core.infrastructure.database.session import DbSession
from src.core.messaging.outbox import SqlAlchemyOutboxWriter
from src.core.uow import UnitOfWork
from src.modules.applications.facade import ApplicationsFacade
from src.modules.clients.facade import ClientsFacade
from src.modules.identity.facade import IdentityFacade
from src.modules.support.application.interfaces.outbox import MessageOutbox
from src.modules.support.application.interfaces.repositories import TicketRepository
from src.modules.support.application.mappers.messages import PRODUCER
from src.modules.support.application.use_cases.client import (
    CloseMyTicketUseCase,
    ListMyTicketsUseCase,
    OpenTicketUseCase,
    PostClientMessageUseCase,
)
from src.modules.support.application.use_cases.common import GetTicketUseCase, TicketChange
from src.modules.support.application.use_cases.staff import (
    CloseTicketUseCase,
    ListQueueUseCase,
    PostStaffMessageUseCase,
    ReleaseTicketUseCase,
    ResolveTicketUseCase,
    TakeTicketUseCase,
)
from src.modules.support.infrastructure.adapters.unit_of_work import SupportUnitOfWork
from src.modules.support.infrastructure.repositories.tickets import SqlAlchemyTicketRepository

# --- access --------------------------------------------------------------------

# The client: own tickets (`own_only`); the admin is not row-restricted.
CanRead = Annotated[AccessContext, Depends(get_access_context_for(Permissions.SUPPORT_READ))]
CanWrite = Annotated[AccessContext, Depends(get_access_context_for(Permissions.SUPPORT_CREATE))]
# The staff queue.
CanManage = Annotated[AccessContext, Depends(get_access_context_for(Permissions.SUPPORT_MANAGE))]


# --- adapters ------------------------------------------------------------------


def get_clock(request: Request) -> Clock:
    return request.app.state.clock


def get_uow(session: DbSession) -> UnitOfWork:
    return SupportUnitOfWork(session)


def get_repository(session: DbSession) -> TicketRepository:
    return SqlAlchemyTicketRepository(session)


def get_outbox(request: Request, session: DbSession) -> MessageOutbox:
    return SqlAlchemyOutboxWriter(session, PRODUCER, request.app.state.clock)


ClockDep = Annotated[Clock, Depends(get_clock)]
Uow = Annotated[UnitOfWork, Depends(get_uow)]
Repository = Annotated[TicketRepository, Depends(get_repository)]
Outbox = Annotated[MessageOutbox, Depends(get_outbox)]
Clients = Annotated[ClientsFacade, Depends(use_facade(ClientsFacade))]
Applications = Annotated[ApplicationsFacade, Depends(use_facade(ApplicationsFacade))]
Identity = Annotated[IdentityFacade, Depends(use_facade(IdentityFacade))]


# --- use cases -----------------------------------------------------------------


def get_open_ticket(
    uow: Uow,
    repository: Repository,
    outbox: Outbox,
    clients: Clients,
    applications: Applications,
    identity: Identity,
    clock: ClockDep,
) -> OpenTicketUseCase:
    return OpenTicketUseCase(uow, repository, outbox, clients, applications, identity, clock)


def get_list_my_tickets(repository: Repository) -> ListMyTicketsUseCase:
    return ListMyTicketsUseCase(repository)


def get_get_ticket(repository: Repository, identity: Identity) -> GetTicketUseCase:
    return GetTicketUseCase(repository, identity)


def get_list_queue(repository: Repository) -> ListQueueUseCase:
    return ListQueueUseCase(repository)


def _change[C: TicketChange](kind: type[C]) -> Callable[..., C]:
    """A dependency building one of the use cases that change a ticket."""

    def dependency(
        uow: Uow, repository: Repository, outbox: Outbox, identity: Identity, clock: ClockDep
    ) -> C:
        return kind(uow, repository, outbox, identity, clock)

    dependency.__name__ = f"get_{kind.__name__}"
    return dependency


OpenTicketDep = Annotated[OpenTicketUseCase, Depends(get_open_ticket)]
ListMyTicketsDep = Annotated[ListMyTicketsUseCase, Depends(get_list_my_tickets)]
GetTicketDep = Annotated[GetTicketUseCase, Depends(get_get_ticket)]
ListQueueDep = Annotated[ListQueueUseCase, Depends(get_list_queue)]
PostClientMessageDep = Annotated[
    PostClientMessageUseCase, Depends(_change(PostClientMessageUseCase))
]
CloseMyTicketDep = Annotated[CloseMyTicketUseCase, Depends(_change(CloseMyTicketUseCase))]
TakeTicketDep = Annotated[TakeTicketUseCase, Depends(_change(TakeTicketUseCase))]
ReleaseTicketDep = Annotated[ReleaseTicketUseCase, Depends(_change(ReleaseTicketUseCase))]
PostStaffMessageDep = Annotated[PostStaffMessageUseCase, Depends(_change(PostStaffMessageUseCase))]
ResolveTicketDep = Annotated[ResolveTicketUseCase, Depends(_change(ResolveTicketUseCase))]
CloseTicketDep = Annotated[CloseTicketUseCase, Depends(_change(CloseTicketUseCase))]
