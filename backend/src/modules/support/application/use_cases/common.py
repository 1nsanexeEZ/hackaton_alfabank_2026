"""What the client and the staff use cases share: the view of a ticket with the
names of its people, the employee behind a token, a change in one transaction."""

from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from src.core.access.access_context import AccessContext
from src.core.access.permissions import Permissions
from src.core.domain.clock import Clock
from src.core.uow import UnitOfWork
from src.modules.identity.facade import IdentityFacade
from src.modules.support.application.dto.tickets import TicketViewDTO
from src.modules.support.application.interfaces.outbox import MessageOutbox
from src.modules.support.application.interfaces.repositories import TicketRepository
from src.modules.support.application.mappers.dto import view_dto
from src.modules.support.application.mappers.messages import stage
from src.modules.support.domain.ticket import SupportTicket
from src.modules.support.domain.value_objects import Staff

# A change of a loaded ticket at a moment; what it returns is not used.
Change = Callable[[SupportTicket, datetime], object]


def staff_of(access: AccessContext) -> Staff:
    """The admin supervises the queue: may act in a ticket taken by someone else."""
    return Staff(access.user_id, supervisor=Permissions.ADMIN.value in access.granted_permissions)


async def view(identity: IdentityFacade, ticket: SupportTicket) -> TicketViewDTO:
    people = {ticket.author_id, *(m.author_id for m in ticket.messages)}
    if ticket.assignee_id is not None:
        people.add(ticket.assignee_id)
    names: dict[UUID, str] = {}
    for account_id in people:
        account = await identity.get_account(account_id)
        if account is not None:
            names[account_id] = " ".join(p for p in (account.first_name, account.last_name) if p)
    return view_dto(ticket, names)


class GetTicketUseCase:
    """The ticket with its chat: the client's own one or, for the staff, any."""

    def __init__(self, repository: TicketRepository, identity: IdentityFacade) -> None:
        self._repository = repository
        self._identity = identity

    async def execute(self, access: AccessContext, ticket_id: UUID) -> TicketViewDTO:
        return await view(self._identity, await self._repository.get(ticket_id, access))


class TicketChange:
    """Load a ticket under the caller's policies, change it, save it with its
    events in one transaction and return the new view."""

    def __init__(
        self,
        uow: UnitOfWork,
        repository: TicketRepository,
        outbox: MessageOutbox,
        identity: IdentityFacade,
        clock: Clock,
    ) -> None:
        self._uow = uow
        self._repository = repository
        self._outbox = outbox
        self._identity = identity
        self._clock = clock

    async def _apply(self, access: AccessContext, ticket_id: UUID, change: Change) -> TicketViewDTO:
        async with self._uow:
            ticket = await self._repository.get(ticket_id, access)
            change(ticket, self._clock.now())
            await self._repository.save(ticket)
            await stage(self._outbox, ticket.pull_events())
            await self._uow.commit()
        return await view(self._identity, ticket)
