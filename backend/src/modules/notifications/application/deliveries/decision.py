"""decision.events -> auto decisions for the back office, advice and
pre-approved offers for the company members."""

from uuid import UUID

from src.core.messaging.contracts.decision import (
    DecisionMade,
    ManualDecisionRejected,
    PreApprovedOffersUpdated,
)
from src.modules.notifications.application.deliveries.context import (
    DeliveryContext,
    Handlers,
    bank_entry,
    client_link,
)
from src.modules.notifications.domain import templates as t
from src.modules.notifications.domain.advice import advice_for
from src.modules.notifications.domain.feed import (
    UNDERWRITERS,
    Delivery,
    FeedEntry,
    pre_approved_group,
)


class DecisionDeliveries:
    def __init__(self, ctx: DeliveryContext) -> None:
        self._ctx = ctx

    def handlers(self) -> Handlers:
        return {
            DecisionMade: self._decision_made,
            ManualDecisionRejected: self._manual_decision_rejected,
            PreApprovedOffersUpdated: self._pre_approved,
        }

    async def _decision_made(self, event: DecisionMade) -> list[Delivery]:
        app = await self._ctx.application(event.application_id)
        deliveries: list[Delivery] = []
        if event.decided_by == "auto":
            rendered = t.BANK_AUTO_DECISION.render(
                number=app.number,
                outcome=t.OUTCOME_TITLES.get(event.outcome, event.outcome),
                explanation=event.client_explanation,
            )
            deliveries.append(Delivery(bank_entry(app, rendered, "low"), (UNDERWRITERS,)))

        members = await self._ctx.members(app.organization_id)
        if not members:
            return deliveries
        for advice in advice_for(await self._signals(app.id), app.product_code):
            link = (
                advice.link.format(application_id=app.id, organization_id=app.organization_id)
                if advice.link
                else None
            )
            entry = FeedEntry(
                type="advice",
                audience="client",
                title=advice.title,
                body=advice.body,
                link=link,
                organization_id=app.organization_id,
                application_id=app.id,
                discriminator=f"advice:{advice.code}",
            )
            deliveries.append(Delivery(entry, members))
        if event.improvement_hints:
            title, body = t.HINTS.render(hints=t.bullets(event.improvement_hints))
            entry = FeedEntry(
                type="advice",
                audience="client",
                title=title,
                body=body,
                link=client_link(app.id),
                priority="low",
                organization_id=app.organization_id,
                application_id=app.id,
                discriminator="advice:hints",
            )
            deliveries.append(Delivery(entry, members))
        return deliveries

    async def _signals(self, application_id: UUID) -> list[str]:
        """Scoring flags and decision reason codes: what the advice is built on."""
        signals: list[str] = []
        scoring = await self._ctx.neighbours.scoring(application_id)
        if scoring is not None:
            signals.extend(scoring.flags)
        decision = await self._ctx.neighbours.decision(application_id)
        if decision is not None:
            signals.extend(decision.reason_codes)
        return signals

    async def _manual_decision_rejected(self, event: ManualDecisionRejected) -> list[Delivery]:
        app = await self._ctx.application(event.application_id)
        rendered = t.BANK_MANUAL_DECISION_REJECTED.render(number=app.number, reason=event.reason)
        entry = bank_entry(
            app, rendered, "high", action_required=True, link=f"/backoffice/tasks/{event.task_id}"
        )
        return [Delivery(entry, (UNDERWRITERS,))]

    async def _pre_approved(self, event: PreApprovedOffersUpdated) -> list[Delivery]:
        offers = await self._ctx.neighbours.pre_approved(event.organization_id)
        if not offers:
            return []
        lines = []
        for offer in offers:
            name = await self._ctx.neighbours.product_name(offer.product_code) or offer.product_code
            lines.append(
                f"{name}: до {t.money(offer.max_amount)}, ставка от {t.rate(offer.rate_from)}, "
                f"срок до {offer.term_max_months} мес."
            )
        title, body = t.PRE_APPROVED.render(offers=t.bullets(lines))
        entry = FeedEntry(
            type="advice",
            audience="client",
            title=title,
            body=body,
            link="/products",
            organization_id=event.organization_id,
            group_key=pre_approved_group(event.organization_id),
        )
        return [Delivery(entry, await self._ctx.members(event.organization_id), replace_group=True)]
