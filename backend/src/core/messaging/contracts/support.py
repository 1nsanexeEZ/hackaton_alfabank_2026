"""support.events — key: ticket_id."""

from uuid import UUID

from src.core.messaging import topics
from src.core.messaging.contracts.base import IntegrationMessage


class SupportTicketEvent(IntegrationMessage):
    ticket_id: UUID
    number: str
    subject: str
    # The client who opened the ticket.
    client_id: UUID
    assignee_id: UUID | None = None
    organization_id: UUID | None = None
    application_id: UUID | None = None


class SupportTicketOpened(SupportTicketEvent):
    TYPE = "SupportTicketOpened"
    TOPIC = topics.SUPPORT_EVENTS


class SupportMessagePosted(SupportTicketEvent):
    TYPE = "SupportMessagePosted"
    TOPIC = topics.SUPPORT_EVENTS

    message_id: UUID
    # `client` or `staff`.
    side: str
    author_id: UUID
    # The beginning of the message, for a notification.
    preview: str


class SupportTicketStatusChanged(SupportTicketEvent):
    TYPE = "SupportTicketStatusChanged"
    TOPIC = topics.SUPPORT_EVENTS

    from_status: str
    to_status: str
    # Who changed it: `client` or `staff`, and their account.
    side: str
    actor_id: UUID
