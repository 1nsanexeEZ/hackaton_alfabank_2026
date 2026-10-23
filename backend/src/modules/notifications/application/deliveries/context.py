"""What the delivery rules of every source topic share: the application and its
company, the recipients, the names and the back office entry. Data missing from
the event (application number, company and product names) is read from
neighbours."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from src.modules.applications.facade import ApplicationCardDTO
from src.modules.notifications.application.interfaces.neighbours import Neighbours
from src.modules.notifications.domain import templates as t
from src.modules.notifications.domain.enums import FeedItemType, Priority
from src.modules.notifications.domain.feed import Delivery, FeedEntry, Recipient

BANK_FALLBACK_NAME = "Клиент"

# Message type -> what an event of it is delivered as.
Handler = Callable[[Any], Awaitable[list[Delivery]]]
Handlers = dict[type[Any], Handler]


def client_link(application_id: UUID) -> str:
    return f"/applications/{application_id}"


def bank_link(application_id: UUID) -> str:
    return f"/backoffice/applications/{application_id}"


@dataclass(frozen=True, slots=True)
class ApplicationRef:
    id: UUID
    organization_id: UUID | None
    number: str
    product_code: str | None
    card: ApplicationCardDTO | None


def bank_entry(
    app: ApplicationRef,
    rendered: tuple[str, str],
    priority: Priority,
    *,
    action_required: bool = False,
    type: FeedItemType = "status_changed",
    link: str | None = None,
    group_key: str | None = None,
) -> FeedEntry:
    title, body = rendered
    return FeedEntry(
        type=type,
        audience="bank",
        title=title,
        body=body,
        link=link or bank_link(app.id),
        priority=priority,
        action_required=action_required,
        organization_id=app.organization_id,
        application_id=app.id,
        group_key=group_key,
    )


class DeliveryContext:
    """One per event: the neighbours cache what they read."""

    def __init__(self, neighbours: Neighbours) -> None:
        self.neighbours = neighbours

    async def application(
        self, application_id: UUID, organization_id: UUID | None = None
    ) -> ApplicationRef:
        card = await self.neighbours.card(application_id)
        return ApplicationRef(
            id=application_id,
            organization_id=organization_id or (card.organization_id if card else None),
            number=t.number_label(card.number if card else None),
            product_code=card.product_code if card else None,
            card=card,
        )

    async def members(self, organization_id: UUID | None) -> tuple[Recipient, ...]:
        if organization_id is None:
            return ()
        accounts = dict.fromkeys(await self.neighbours.members(organization_id))
        return tuple(Recipient.account(account_id) for account_id in accounts)

    async def organization_name(
        self, organization_id: UUID | None, card: ApplicationCardDTO | None = None
    ) -> str | None:
        """The name frozen in the application, else the current one of the company."""
        if card is not None and card.org_snapshot is not None:
            return card.org_snapshot.name
        if organization_id is None:
            return None
        snapshot = await self.neighbours.organization(organization_id)
        return snapshot.name if snapshot else None

    async def bank_name(self, app: ApplicationRef) -> str:
        name = await self.organization_name(app.organization_id, app.card)
        return name or BANK_FALLBACK_NAME

    async def client_name(self, organization_id: UUID) -> str:
        return await self.organization_name(organization_id) or ""
