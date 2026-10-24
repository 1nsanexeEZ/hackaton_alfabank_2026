"""Domain events of a ticket. The application layer maps them to
`support.events` contracts before they go to the outbox."""

from dataclasses import dataclass
from uuid import UUID

from src.core.domain import DomainEvent


@dataclass(frozen=True, kw_only=True)
class TicketEvent(DomainEvent):
    ticket_id: UUID
    number: str
    subject: str
    # The client who opened the ticket.
    client_id: UUID
    assignee_id: UUID | None
    organization_id: UUID | None
    application_id: UUID | None


@dataclass(frozen=True, kw_only=True)
class TicketOpened(TicketEvent):
    pass


@dataclass(frozen=True, kw_only=True)
class MessagePosted(TicketEvent):
    message_id: UUID
    side: str
    author_id: UUID
    text: str


@dataclass(frozen=True, kw_only=True)
class TicketStatusChanged(TicketEvent):
    from_status: str
    to_status: str
    # Who changed it: the client or an employee, and their account.
    side: str
    actor_id: UUID
