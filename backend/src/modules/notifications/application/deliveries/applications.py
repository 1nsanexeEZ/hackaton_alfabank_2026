"""applications.events -> entries for the company members and the back office."""

from typing import Any

from src.core.messaging.contracts.applications import (
    ApplicationCancelled,
    ApplicationInfoProvided,
    ApplicationSigned,
    ApplicationStatusChanged,
    ApplicationSubmitted,
    OfferAccepted,
    OfferDeclined,
)
from src.modules.applications.facade import ApplicationCardDTO
from src.modules.notifications.application.deliveries.context import (
    DeliveryContext,
    Handler,
    Handlers,
    bank_entry,
    client_link,
)
from src.modules.notifications.domain import templates as t
from src.modules.notifications.domain.enums import Priority
from src.modules.notifications.domain.feed import UNDERWRITERS, Delivery, FeedEntry


class ApplicationDeliveries:
    def __init__(self, ctx: DeliveryContext) -> None:
        self._ctx = ctx

    def handlers(self) -> Handlers:
        return {
            ApplicationSubmitted: self._submitted,
            ApplicationStatusChanged: self._status_changed,
            ApplicationInfoProvided: self._info_provided,
            OfferAccepted: self._bank_note(t.BANK_OFFER_ACCEPTED, "low"),
            OfferDeclined: self._bank_note(t.BANK_OFFER_DECLINED, "low"),
            ApplicationSigned: self._bank_note(t.BANK_SIGNED, "normal"),
            ApplicationCancelled: self._bank_note(t.BANK_CANCELLED, "low"),
        }

    def _bank_note(self, template: t.Template, priority: Priority) -> Handler:
        async def handle(event: Any) -> list[Delivery]:
            app = await self._ctx.application(event.application_id, event.organization_id)
            rendered = template.render(
                number=app.number, organization=await self._ctx.bank_name(app)
            )
            return [Delivery(bank_entry(app, rendered, priority), (UNDERWRITERS,))]

        return handle

    async def _submitted(self, event: ApplicationSubmitted) -> list[Delivery]:
        app = await self._ctx.application(event.application_id, event.organization_id)
        product = await self._ctx.neighbours.product_name(event.product_code) or event.product_code
        values = {
            "number": app.number,
            "product": product,
            "amount": t.money(event.amount),
            "term": event.term_months,
        }
        title, body = t.SUBMITTED.render(**values)
        client = FeedEntry(
            type="status_changed",
            audience="client",
            title=title,
            body=body,
            link=client_link(app.id),
            organization_id=event.organization_id,
            application_id=app.id,
        )
        bank = bank_entry(
            app,
            t.BANK_SUBMITTED.render(**values, organization=await self._ctx.bank_name(app)),
            "low",
        )
        return [
            Delivery(client, await self._ctx.members(event.organization_id)),
            Delivery(bank, (UNDERWRITERS,)),
        ]

    async def _status_changed(self, event: ApplicationStatusChanged) -> list[Delivery]:
        key = event.to_status
        if key == "in_review" and event.from_status == "info_requested":
            key = "in_review_after_info"
        template = t.STATUS.get(key)
        if template is None:  # draft, submitted (see ApplicationSubmitted)
            return []
        app = await self._ctx.application(event.application_id, event.organization_id)
        title, body = template.render(number=app.number, **_status_values(key, app.card))
        entry = FeedEntry(
            type=template.type,
            audience="client",
            title=title,
            body=body,
            link=client_link(app.id),
            priority=template.priority,
            action_required=template.action_required,
            organization_id=event.organization_id,
            application_id=app.id,
        )
        return [Delivery(entry, await self._ctx.members(event.organization_id))]

    async def _info_provided(self, event: ApplicationInfoProvided) -> list[Delivery]:
        app = await self._ctx.application(event.application_id, event.organization_id)
        rendered = t.BANK_INFO_PROVIDED.render(
            number=app.number,
            organization=await self._ctx.bank_name(app),
            documents=len(event.document_ids),
        )
        return [Delivery(bank_entry(app, rendered, "normal"), (UNDERWRITERS,))]


def _status_values(key: str, card: ApplicationCardDTO | None) -> dict[str, object]:
    if key == "info_requested":
        requests = sorted(
            (r for r in (card.info_requests if card else ()) if r.status == "open"),
            key=lambda r: r.created_at,
        )
        if not requests:
            return {"comment": t.DEFAULT_INFO_COMMENT, "documents": ""}
        request = requests[-1]
        documents = ", ".join(t.DOCUMENT_TITLES.get(d, d) for d in request.requested_documents)
        return {
            "comment": request.comment or t.DEFAULT_INFO_COMMENT,
            "documents": t.INFO_DOCUMENTS.fragment(documents=documents) if documents else "",
        }
    if key == "offer_ready":
        offer = card.offer if card else None
        if offer is None:
            return {"offer": ""}
        return {
            "offer": t.OFFER.fragment(
                amount=t.money(offer.amount),
                term=offer.term_months,
                rate=t.rate(offer.rate),
                payment=t.money(offer.monthly_payment),
                until=t.day(offer.expires_at),
            )
        }
    if key == "rejected":
        summary = card.decision_summary if card else None
        explanation = summary.client_explanation if summary else ""
        return {"explanation": explanation or t.DEFAULT_REJECTION}
    return {}
