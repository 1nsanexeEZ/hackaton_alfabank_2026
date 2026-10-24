"""Ticket aggregate -> DTO of the API."""

from collections.abc import Mapping
from uuid import UUID

from src.modules.support.application.dto.tickets import (
    MessageDTO,
    TicketSummaryDTO,
    TicketViewDTO,
)
from src.modules.support.domain.ticket import SupportTicket


def summary_dto(ticket: SupportTicket) -> TicketSummaryDTO:
    last = ticket.last_message
    return TicketSummaryDTO(
        id=ticket.id,
        number=str(ticket.number),
        subject=ticket.subject,
        status=ticket.status,
        author_id=ticket.author_id,
        organization_id=ticket.organization_id,
        application_id=ticket.application_id,
        assignee_id=ticket.assignee_id,
        taken_at=ticket.taken_at,
        resolved_at=ticket.resolved_at,
        closed_at=ticket.closed_at,
        message_count=len(ticket.messages),
        last_message_at=last.created_at if last else None,
        last_message_side=last.side if last else None,
        version=ticket.version,
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
    )


def view_dto(ticket: SupportTicket, names: Mapping[UUID, str]) -> TicketViewDTO:
    """`names` — display names of the people in the ticket, by account id."""
    summary = summary_dto(ticket)
    return TicketViewDTO(
        **{field: getattr(summary, field) for field in TicketSummaryDTO.__dataclass_fields__},
        author_name=names.get(ticket.author_id),
        assignee_name=names.get(ticket.assignee_id) if ticket.assignee_id else None,
        messages=tuple(
            MessageDTO(
                id=message.id,
                author_id=message.author_id,
                author_name=names.get(message.author_id),
                side=message.side,
                text=message.text,
                created_at=message.created_at,
            )
            for message in ticket.messages
        ),
    )
