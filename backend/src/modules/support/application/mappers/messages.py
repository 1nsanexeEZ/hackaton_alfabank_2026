"""Domain events -> `support.events` contracts, staged in the outbox in the
transaction of the change. Key and correlation — ticket_id."""

from collections.abc import Iterable

from src.core.messaging.contracts import support as contracts
from src.core.messaging.contracts.base import IntegrationMessage
from src.modules.support.application.interfaces.outbox import MessageOutbox
from src.modules.support.domain import events as domain

PRODUCER = "support"
# A notification shows the beginning of a message, not the whole chat.
PREVIEW_LENGTH = 200


def preview(text: str) -> str:
    if len(text) <= PREVIEW_LENGTH:
        return text
    return text[: PREVIEW_LENGTH - 1].rstrip() + "…"


def to_contract(event: domain.TicketEvent) -> IntegrationMessage:
    common = {
        "ticket_id": event.ticket_id,
        "number": event.number,
        "subject": event.subject,
        "client_id": event.client_id,
        "assignee_id": event.assignee_id,
        "organization_id": event.organization_id,
        "application_id": event.application_id,
    }
    match event:
        case domain.TicketOpened():
            return contracts.SupportTicketOpened.model_validate(common)
        case domain.MessagePosted():
            return contracts.SupportMessagePosted.model_validate(
                common
                | {
                    "message_id": event.message_id,
                    "side": event.side,
                    "author_id": event.author_id,
                    "preview": preview(event.text),
                }
            )
        case domain.TicketStatusChanged():
            return contracts.SupportTicketStatusChanged.model_validate(
                common
                | {
                    "from_status": event.from_status,
                    "to_status": event.to_status,
                    "side": event.side,
                    "actor_id": event.actor_id,
                }
            )
    raise TypeError(f"No contract for {type(event).__name__}")


async def stage(outbox: MessageOutbox, events: Iterable[domain.TicketEvent]) -> None:
    for event in events:
        await outbox.add(to_contract(event), key=event.ticket_id, correlation_id=event.ticket_id)
