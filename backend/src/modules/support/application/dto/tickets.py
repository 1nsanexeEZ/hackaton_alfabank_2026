from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from src.modules.support.domain.enums import Side, TicketStatus

# Staff queue: every ticket, only the ones nobody has taken, only the caller's.
QueueScope = Literal["all", "unassigned", "mine"]


@dataclass(frozen=True, slots=True)
class NewTicketDTO:
    subject: str
    text: str
    # Optional: the company and the application the question is about.
    organization_id: UUID | None = None
    application_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class TicketQuery:
    """Filters of a ticket list; the caller's row policies come with the AccessContext."""

    statuses: tuple[TicketStatus, ...] = ()
    unassigned: bool = False
    assignee_id: UUID | None = None
    limit: int = 20
    offset: int = 0


@dataclass(frozen=True, slots=True)
class MessageDTO:
    id: UUID
    author_id: UUID
    # Name of the person; None when the account is not found.
    author_name: str | None
    side: Side
    text: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class TicketSummaryDTO:
    id: UUID
    number: str
    subject: str
    status: TicketStatus
    author_id: UUID
    organization_id: UUID | None
    application_id: UUID | None
    assignee_id: UUID | None
    taken_at: datetime | None
    resolved_at: datetime | None
    closed_at: datetime | None
    message_count: int
    last_message_at: datetime | None
    # Who wrote last: `client` in a ticket that is not closed — the bank owes an answer.
    last_message_side: Side | None
    version: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class TicketViewDTO(TicketSummaryDTO):
    author_name: str | None
    assignee_name: str | None
    messages: tuple[MessageDTO, ...]
