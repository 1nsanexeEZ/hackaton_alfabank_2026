"""support.events -> the client's entry of a ticket, the queue entry for the back office.

- A new ticket: the back office role, action required until somebody takes it
  (or the client closes it) — ProjectEventUseCase resolves the group then.
- An answer of an employee, taken / resolved / closed by an employee: the client.
  One entry per ticket, replaced by the latest one: the feed does not repeat the chat.
- A client message in a taken ticket: the employee who took it.
- Returned to the queue: the back office role again.
"""

from src.core.messaging.contracts.support import (
    SupportMessagePosted,
    SupportTicketEvent,
    SupportTicketOpened,
    SupportTicketStatusChanged,
)
from src.modules.notifications.application.deliveries.context import DeliveryContext, Handlers
from src.modules.notifications.domain import templates as t
from src.modules.notifications.domain.enums import Audience
from src.modules.notifications.domain.feed import (
    UNDERWRITERS,
    Delivery,
    FeedEntry,
    Recipient,
    support_assignee_group,
    support_client_group,
    support_queue_group,
)

STAFF = "staff"


def client_link(event: SupportTicketEvent) -> str:
    return f"/support/{event.ticket_id}"


def bank_link(event: SupportTicketEvent) -> str:
    return f"/backoffice/support/{event.ticket_id}"


def entry(
    event: SupportTicketEvent,
    audience: Audience,
    rendered: tuple[str, str],
    group_key: str,
    *,
    action_required: bool = False,
) -> FeedEntry:
    title, body = rendered
    return FeedEntry(
        type="support",
        audience=audience,
        title=title,
        body=body,
        link=client_link(event) if audience == "client" else bank_link(event),
        action_required=action_required,
        organization_id=event.organization_id,
        application_id=event.application_id,
        group_key=group_key,
    )


class SupportDeliveries:
    def __init__(self, ctx: DeliveryContext) -> None:
        self._ctx = ctx

    def handlers(self) -> Handlers:
        return {
            SupportTicketOpened: self._opened,
            SupportMessagePosted: self._message,
            SupportTicketStatusChanged: self._status,
        }

    async def _opened(self, event: SupportTicketOpened) -> list[Delivery]:
        organization = ""
        if event.organization_id is not None:
            organization = await self._ctx.client_name(event.organization_id)
        rendered = t.BANK_SUPPORT_OPENED.render(
            number=event.number, subject=event.subject, organization=organization
        )
        queued = entry(
            event, "bank", rendered, support_queue_group(event.ticket_id), action_required=True
        )
        return [Delivery(queued, (UNDERWRITERS,), replace_group=True)]

    async def _message(self, event: SupportMessagePosted) -> list[Delivery]:
        values = {"number": event.number, "subject": event.subject, "preview": event.preview}
        if event.side == STAFF:
            rendered = t.SUPPORT_REPLY.render(**values)
            reply = entry(event, "client", rendered, support_client_group(event.ticket_id))
            return [Delivery(reply, (Recipient.account(event.client_id),), replace_group=True)]
        if event.assignee_id is None:
            return []  # still in the queue: the queue entry is there
        rendered = t.BANK_SUPPORT_CLIENT_WROTE.render(**values)
        wrote = entry(event, "bank", rendered, support_assignee_group(event.ticket_id))
        return [Delivery(wrote, (Recipient.account(event.assignee_id),), replace_group=True)]

    async def _status(self, event: SupportTicketStatusChanged) -> list[Delivery]:
        values = {"number": event.number, "subject": event.subject}
        if event.to_status == "open":
            rendered = t.BANK_SUPPORT_RETURNED.render(**values)
            queued = entry(
                event, "bank", rendered, support_queue_group(event.ticket_id), action_required=True
            )
            return [Delivery(queued, (UNDERWRITERS,), replace_group=True)]
        template = t.SUPPORT_STATUS.get(event.to_status)
        if event.side != STAFF or template is None:
            return []  # the client did it: nothing to tell them
        rendered = template.render(**values)
        status = entry(event, "client", rendered, support_client_group(event.ticket_id))
        return [Delivery(status, (Recipient.account(event.client_id),), replace_group=True)]
