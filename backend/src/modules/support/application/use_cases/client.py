"""The client's side: open a ticket, read own tickets, write into one, close it.

Row access comes with the AccessContext: the client's `support.*` carry the
`own_only` policy, so somebody else's ticket is 404. The admin is not
row-restricted; writing as the client is still only for the author (domain).
"""

from collections.abc import Sequence
from uuid import UUID, uuid4

from src.core.access.access_context import AccessContext
from src.core.domain.clock import Clock
from src.core.exceptions.exceptions import NotFoundError, ValidationError
from src.core.uow import UnitOfWork
from src.modules.applications.facade import ApplicationsFacade
from src.modules.clients.facade import ClientsFacade, OrgPermission
from src.modules.identity.facade import IdentityFacade
from src.modules.support.application.dto.tickets import (
    NewTicketDTO,
    TicketQuery,
    TicketSummaryDTO,
    TicketViewDTO,
)
from src.modules.support.application.interfaces.outbox import MessageOutbox
from src.modules.support.application.interfaces.repositories import TicketRepository
from src.modules.support.application.mappers.dto import summary_dto
from src.modules.support.application.mappers.messages import stage
from src.modules.support.application.use_cases.common import TicketChange, view
from src.modules.support.domain.enums import TicketStatus
from src.modules.support.domain.ticket import SupportTicket


class OpenTicketUseCase:
    """A ticket with the first message. The company and the application are
    optional; when given, the client must be a member of the company (a
    stranger's company or application is 404)."""

    def __init__(
        self,
        uow: UnitOfWork,
        repository: TicketRepository,
        outbox: MessageOutbox,
        clients: ClientsFacade,
        applications: ApplicationsFacade,
        identity: IdentityFacade,
        clock: Clock,
    ) -> None:
        self._uow = uow
        self._repository = repository
        self._outbox = outbox
        self._clients = clients
        self._applications = applications
        self._identity = identity
        self._clock = clock

    async def execute(self, access: AccessContext, data: NewTicketDTO) -> TicketViewDTO:
        organization_id = await self._organization_of(access.user_id, data)
        now = self._clock.now()
        ticket = SupportTicket.open(
            id=uuid4(),
            number=await self._repository.next_number(now.year),
            author_id=access.user_id,
            subject=data.subject,
            text=data.text,
            message_id=uuid4(),
            now=now,
            organization_id=organization_id,
            application_id=data.application_id,
        )
        async with self._uow:
            await self._repository.add(ticket)
            await stage(self._outbox, ticket.pull_events())
            await self._uow.commit()
        return await view(self._identity, ticket)

    async def _organization_of(self, account_id: UUID, data: NewTicketDTO) -> UUID | None:
        if data.application_id is None:
            if data.organization_id is not None:
                await self._clients.ensure_can(account_id, data.organization_id, OrgPermission.VIEW)
            return data.organization_id
        card = await self._applications.get_card(data.application_id)
        try:
            await self._clients.ensure_can(account_id, card.organization_id, OrgPermission.VIEW)
        except NotFoundError:
            raise NotFoundError("Application not found") from None
        if data.organization_id is not None and data.organization_id != card.organization_id:
            raise ValidationError(
                "The application belongs to another company",
                details={"field": "application_id"},
            )
        # The company of the application, even when the client did not name it.
        return card.organization_id


class ListMyTicketsUseCase:
    def __init__(self, repository: TicketRepository) -> None:
        self._repository = repository

    async def execute(
        self,
        access: AccessContext,
        statuses: Sequence[TicketStatus],
        limit: int,
        offset: int,
    ) -> tuple[list[TicketSummaryDTO], int]:
        """A page and the total."""
        query = TicketQuery(statuses=tuple(statuses), limit=limit, offset=offset)
        tickets = await self._repository.search(access, query)
        return [summary_dto(t) for t in tickets], await self._repository.count(access, query)


class PostClientMessageUseCase(TicketChange):
    """A message into the client's ticket that is not closed; a resolved one
    goes back to the employee who handled it."""

    async def execute(self, access: AccessContext, ticket_id: UUID, text: str) -> TicketViewDTO:
        return await self._apply(
            access,
            ticket_id,
            lambda ticket, now: ticket.post_client_message(access.user_id, uuid4(), text, now),
        )


class CloseMyTicketUseCase(TicketChange):
    async def execute(self, access: AccessContext, ticket_id: UUID) -> TicketViewDTO:
        return await self._apply(
            access, ticket_id, lambda ticket, now: ticket.close_by_client(access.user_id, now)
        )
