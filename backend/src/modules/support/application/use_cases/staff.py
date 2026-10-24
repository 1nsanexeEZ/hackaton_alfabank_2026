"""The staff side (`support.manage`): the queue, take a ticket, answer, resolve,
close, return to the queue. Who may act in a taken ticket — the domain decides
(the employee who took it; the admin as a supervisor)."""

from collections.abc import Sequence
from uuid import UUID, uuid4

from src.core.access.access_context import AccessContext
from src.modules.support.application.dto.tickets import (
    QueueScope,
    TicketQuery,
    TicketSummaryDTO,
    TicketViewDTO,
)
from src.modules.support.application.interfaces.repositories import (
    TicketChangedError,
    TicketRepository,
)
from src.modules.support.application.mappers.dto import summary_dto
from src.modules.support.application.use_cases.common import TicketChange, staff_of
from src.modules.support.domain.enums import TicketStatus


class ListQueueUseCase:
    def __init__(self, repository: TicketRepository) -> None:
        self._repository = repository

    async def execute(
        self,
        access: AccessContext,
        statuses: Sequence[TicketStatus],
        scope: QueueScope,
        limit: int,
        offset: int,
    ) -> list[TicketSummaryDTO]:
        query = TicketQuery(
            statuses=tuple(statuses),
            unassigned=scope == "unassigned",
            assignee_id=access.user_id if scope == "mine" else None,
            limit=limit,
            offset=offset,
        )
        return [summary_dto(t) for t in await self._repository.search(access, query)]


class TakeTicketUseCase(TicketChange):
    """The ticket becomes the caller's. Taken already — 409 `already_taken`.

    Two employees taking it at once: both read version N, the first write
    moves it to N+1, the second write matches no row and is rolled back. That
    one is tried once more on fresh data: now the ticket is taken — 409
    `already_taken` (and if the concurrent change was something else, say a
    client message, the take goes through)."""

    async def execute(self, access: AccessContext, ticket_id: UUID) -> TicketViewDTO:
        staff = staff_of(access)
        try:
            return await self._apply(access, ticket_id, lambda t, now: t.take(staff, now))
        except TicketChangedError:
            return await self._apply(access, ticket_id, lambda t, now: t.take(staff, now))


class ReleaseTicketUseCase(TicketChange):
    """Back to the queue, nobody's again."""

    async def execute(self, access: AccessContext, ticket_id: UUID) -> TicketViewDTO:
        staff = staff_of(access)
        return await self._apply(access, ticket_id, lambda t, now: t.release(staff, now))


class PostStaffMessageUseCase(TicketChange):
    async def execute(self, access: AccessContext, ticket_id: UUID, text: str) -> TicketViewDTO:
        staff = staff_of(access)
        return await self._apply(
            access, ticket_id, lambda t, now: t.post_staff_message(staff, uuid4(), text, now)
        )


class ResolveTicketUseCase(TicketChange):
    async def execute(self, access: AccessContext, ticket_id: UUID) -> TicketViewDTO:
        staff = staff_of(access)
        return await self._apply(access, ticket_id, lambda t, now: t.resolve(staff, now))


class CloseTicketUseCase(TicketChange):
    async def execute(self, access: AccessContext, ticket_id: UUID) -> TicketViewDTO:
        staff = staff_of(access)
        return await self._apply(access, ticket_id, lambda t, now: t.close_by_staff(staff, now))
