from typing import Protocol
from uuid import UUID

from src.core.access.access_context import AccessContext
from src.core.exceptions.exceptions import ConflictError
from src.modules.support.application.dto.tickets import TicketQuery
from src.modules.support.domain.ticket import SupportTicket
from src.modules.support.domain.value_objects import TicketNumber


class TicketChangedError(ConflictError):
    """The ticket was changed by another transaction after it was read (its
    version moved on). The unit of work raises it after the rollback."""

    def __init__(self) -> None:
        super().__init__(
            "The ticket was changed by someone else, reload it",
            details={"code": "version_conflict"},
        )


class TicketRepository(Protocol):
    async def next_number(self, year: int) -> TicketNumber: ...

    async def add(self, ticket: SupportTicket) -> None: ...

    async def get(self, ticket_id: UUID, access: AccessContext | None = None) -> SupportTicket:
        """NotFoundError when missing or hidden by the caller's policies (`own_only`)."""
        ...

    async def save(self, ticket: SupportTicket) -> None:
        """Only a ticket this repository loaded. The write checks the version the
        ticket was read with; the unit of work turns a lost race into TicketChangedError."""
        ...

    async def search(self, access: AccessContext, query: TicketQuery) -> list[SupportTicket]:
        """Newest activity first."""
        ...

    async def count(self, access: AccessContext, query: TicketQuery) -> int:
        """How many tickets `search` pages through (`limit` and `offset` aside)."""
        ...
