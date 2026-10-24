"""ORM records <-> the ticket aggregate."""

from src.modules.support.domain.entities import TicketMessage
from src.modules.support.domain.enums import Side, TicketStatus
from src.modules.support.domain.ticket import SupportTicket
from src.modules.support.domain.value_objects import TicketNumber
from src.modules.support.infrastructure.database.models import MessageRecord, TicketRecord


def to_domain(record: TicketRecord) -> SupportTicket:
    return SupportTicket(
        id=record.id,
        number=TicketNumber(record.number),
        author_id=record.owner_id,
        subject=record.subject,
        status=TicketStatus(record.status),
        organization_id=record.organization_id,
        application_id=record.application_id,
        assignee_id=record.assignee_id,
        taken_at=record.taken_at,
        resolved_at=record.resolved_at,
        closed_at=record.closed_at,
        messages=[
            TicketMessage(
                id=m.id,
                author_id=m.author_id,
                side=Side(m.side),
                text=m.text,
                created_at=m.created_at,
            )
            for m in record.messages
        ],
        version=record.version,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def new_record(ticket: SupportTicket) -> TicketRecord:
    record = TicketRecord(
        id=ticket.id,
        number=str(ticket.number),
        owner_id=ticket.author_id,
        subject=ticket.subject,
        created_at=ticket.created_at,
        organization_id=ticket.organization_id,
        application_id=ticket.application_id,
        messages=[],
    )
    apply(ticket, record)
    return record


def apply(ticket: SupportTicket, record: TicketRecord) -> None:
    """What may change after the ticket is opened: status, handler, new messages."""
    record.status = ticket.status.value
    record.assignee_id = ticket.assignee_id
    record.taken_at = ticket.taken_at
    record.resolved_at = ticket.resolved_at
    record.closed_at = ticket.closed_at
    record.updated_at = ticket.updated_at
    stored = {m.id for m in record.messages}
    for position, message in enumerate(ticket.messages, start=1):
        if message.id not in stored:
            record.messages.append(
                MessageRecord(
                    id=message.id,
                    position=position,
                    author_id=message.author_id,
                    side=message.side.value,
                    text=message.text,
                    created_at=message.created_at,
                )
            )
