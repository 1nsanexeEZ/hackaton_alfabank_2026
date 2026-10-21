"""Business events -> feed records.

Every handled event becomes zero or more Deliveries: an entry (rendered text,
type, priority) and its recipients — the members of the company
(`ClientsFacade.list_members`) or the back office role. Data missing from the
event (application number, company and product names) is read from neighbours.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from src.applications.facade import ApplicationCardDTO
from src.core.messaging.contracts.applications import (
    ApplicationCancelled,
    ApplicationInfoProvided,
    ApplicationSigned,
    ApplicationStatusChanged,
    ApplicationSubmitted,
    OfferAccepted,
    OfferDeclined,
)
from src.core.messaging.contracts.base import IntegrationMessage
from src.core.messaging.contracts.clients import (
    FinancialReportSubmitted,
    MemberAdded,
    MemberRemoved,
    MemberRoleChanged,
    OrganizationVerificationMismatch,
    OrganizationVerified,
)
from src.core.messaging.contracts.decision import (
    DecisionMade,
    ManualDecisionRejected,
    PreApprovedOffersUpdated,
)
from src.core.messaging.contracts.process import (
    ProcessFailed,
    StepCompleted,
    UserTaskCompleted,
    UserTaskCreated,
)
from src.notifications.application.neighbours import Neighbours
from src.notifications.application.ports import FeedStore
from src.notifications.domain import templates as t
from src.notifications.domain.advice import advice_for
from src.notifications.domain.feed import (
    UNDERWRITERS,
    Delivery,
    FeedEntry,
    Priority,
    Recipient,
    pre_approved_group,
    stage_group,
    task_group,
)
from src.notifications.facade import FeedItemType

BANK_FALLBACK_NAME = "Клиент"

HANDLED_MESSAGES: tuple[type[IntegrationMessage], ...] = (
    ApplicationSubmitted,
    ApplicationStatusChanged,
    ApplicationInfoProvided,
    OfferAccepted,
    OfferDeclined,
    ApplicationSigned,
    ApplicationCancelled,
    StepCompleted,
    UserTaskCreated,
    UserTaskCompleted,
    ProcessFailed,
    DecisionMade,
    ManualDecisionRejected,
    PreApprovedOffersUpdated,
    OrganizationVerified,
    OrganizationVerificationMismatch,
    MemberAdded,
    MemberRemoved,
    MemberRoleChanged,
    FinancialReportSubmitted,
)


def handled_types(topic: str) -> frozenset[str]:
    """Message types of the topic the feed reacts to (filter of the subscription)."""
    return frozenset(m.TYPE for m in HANDLED_MESSAGES if m.TOPIC == topic)


def client_link(application_id: UUID) -> str:
    return f"/applications/{application_id}"


def bank_link(application_id: UUID) -> str:
    return f"/backoffice/applications/{application_id}"


@dataclass(frozen=True, slots=True)
class _Application:
    id: UUID
    organization_id: UUID | None
    number: str
    product_code: str | None
    card: ApplicationCardDTO | None


class FeedProjector:
    def __init__(self, store: FeedStore, neighbours: Neighbours) -> None:
        self._store = store
        self._nb = neighbours
        self._handlers: dict[type[Any], Callable[[Any], Awaitable[list[Delivery]]]] = {
            ApplicationSubmitted: self._submitted,
            ApplicationStatusChanged: self._status_changed,
            ApplicationInfoProvided: self._info_provided,
            OfferAccepted: self._bank_note(t.BANK_OFFER_ACCEPTED, "low"),
            OfferDeclined: self._bank_note(t.BANK_OFFER_DECLINED, "low"),
            ApplicationSigned: self._bank_note(t.BANK_SIGNED, "normal"),
            ApplicationCancelled: self._bank_note(t.BANK_CANCELLED, "low"),
            StepCompleted: self._step_completed,
            UserTaskCreated: self._task_created,
            ProcessFailed: self._process_failed,
            DecisionMade: self._decision_made,
            ManualDecisionRejected: self._manual_decision_rejected,
            PreApprovedOffersUpdated: self._pre_approved,
            OrganizationVerified: self._organization_verified,
            OrganizationVerificationMismatch: self._organization_mismatch,
            MemberAdded: self._member_added,
            MemberRemoved: self._member_removed,
            MemberRoleChanged: self._member_role_changed,
            FinancialReportSubmitted: self._report_submitted,
        }

    async def project(self, message: IntegrationMessage, event_id: UUID, now: datetime) -> int:
        """Write the feed records of one event; returns how many were written."""
        if isinstance(message, UserTaskCompleted):
            return await self._store.resolve_group(task_group(message.task_id), now)
        written = 0
        for delivery in await self.deliveries(message):
            if delivery.recipients:
                written += await self._store.append(delivery, event_id, message.TYPE, now)
        return written

    async def deliveries(self, message: IntegrationMessage) -> list[Delivery]:
        handler = self._handlers.get(type(message))
        return await handler(message) if handler is not None else []

    # --- helpers -------------------------------------------------------------

    async def _application(
        self, application_id: UUID, organization_id: UUID | None = None
    ) -> _Application:
        card = await self._nb.card(application_id)
        return _Application(
            id=application_id,
            organization_id=organization_id or (card.organization_id if card else None),
            number=t.number_label(card.number if card else None),
            product_code=card.product_code if card else None,
            card=card,
        )

    async def _members(self, organization_id: UUID | None) -> tuple[Recipient, ...]:
        if organization_id is None:
            return ()
        accounts = dict.fromkeys(await self._nb.members(organization_id))
        return tuple(Recipient.account(account_id) for account_id in accounts)

    async def _bank_name(self, app: _Application) -> str:
        name = await self._nb.organization_name(app.organization_id, app.card)
        return name or BANK_FALLBACK_NAME

    async def _client_name(self, organization_id: UUID) -> str:
        return await self._nb.organization_name(organization_id) or ""

    def _bank_entry(
        self,
        app: _Application,
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

    def _bank_note(
        self, template: t.Template, priority: Priority
    ) -> Callable[[Any], Awaitable[list[Delivery]]]:
        async def handle(event: Any) -> list[Delivery]:
            app = await self._application(event.application_id, event.organization_id)
            rendered = template.render(number=app.number, organization=await self._bank_name(app))
            return [Delivery(self._bank_entry(app, rendered, priority), (UNDERWRITERS,))]

        return handle

    # --- applications.events ---------------------------------------------------

    async def _submitted(self, event: ApplicationSubmitted) -> list[Delivery]:
        app = await self._application(event.application_id, event.organization_id)
        product = await self._nb.product_name(event.product_code) or event.product_code
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
        bank = self._bank_entry(
            app,
            t.BANK_SUBMITTED.render(**values, organization=await self._bank_name(app)),
            "low",
        )
        return [
            Delivery(client, await self._members(event.organization_id)),
            Delivery(bank, (UNDERWRITERS,)),
        ]

    async def _status_changed(self, event: ApplicationStatusChanged) -> list[Delivery]:
        key = event.to_status
        if key == "in_review" and event.from_status == "info_requested":
            key = "in_review_after_info"
        template = t.STATUS.get(key)
        if template is None:  # draft, submitted (see ApplicationSubmitted)
            return []
        app = await self._application(event.application_id, event.organization_id)
        title, body = template.render(number=app.number, **self._status_values(key, app.card))
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
        return [Delivery(entry, await self._members(event.organization_id))]

    @staticmethod
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

    async def _info_provided(self, event: ApplicationInfoProvided) -> list[Delivery]:
        app = await self._application(event.application_id, event.organization_id)
        rendered = t.BANK_INFO_PROVIDED.render(
            number=app.number,
            organization=await self._bank_name(app),
            documents=len(event.document_ids),
        )
        return [Delivery(self._bank_entry(app, rendered, "normal"), (UNDERWRITERS,))]

    # --- process.events ----------------------------------------------------------

    async def _step_completed(self, event: StepCompleted) -> list[Delivery]:
        if not event.client_stage:
            return []  # an internal step the client does not see
        app = await self._application(event.application_id)
        title, body = t.STAGE.render(stage=event.client_stage, number=app.number)
        entry = FeedEntry(
            type="stage_changed",
            audience="client",
            title=title,
            body=body,
            link=client_link(app.id),
            priority="low",
            organization_id=app.organization_id,
            application_id=app.id,
            group_key=stage_group(app.id),
        )
        return [Delivery(entry, await self._members(app.organization_id), replace_group=True)]

    async def _task_created(self, event: UserTaskCreated) -> list[Delivery]:
        app = await self._application(event.application_id)
        due = f"Срок — до {t.day(event.due_at)}." if event.due_at else ""
        rendered = t.BANK_TASK.render(
            task=t.TASK_TITLES.get(event.task_type, event.task_type),
            number=app.number,
            organization=await self._bank_name(app),
            due=due,
        )
        entry = self._bank_entry(
            app,
            rendered,
            "high",
            action_required=True,
            type="task_assigned",
            link=f"/backoffice/tasks/{event.task_id}",
            group_key=task_group(event.task_id),
        )
        return [Delivery(entry, (Recipient.role(event.candidate_role),))]

    async def _process_failed(self, event: ProcessFailed) -> list[Delivery]:
        app = await self._application(event.application_id)
        rendered = t.BANK_PROCESS_FAILED.render(number=app.number, reason=event.reason)
        entry = self._bank_entry(app, rendered, "high", action_required=True)
        return [Delivery(entry, (UNDERWRITERS,))]

    # --- decision.events ---------------------------------------------------------

    async def _decision_made(self, event: DecisionMade) -> list[Delivery]:
        app = await self._application(event.application_id)
        deliveries: list[Delivery] = []
        if event.decided_by == "auto":
            rendered = t.BANK_AUTO_DECISION.render(
                number=app.number,
                outcome=t.OUTCOME_TITLES.get(event.outcome, event.outcome),
                explanation=event.client_explanation,
            )
            deliveries.append(Delivery(self._bank_entry(app, rendered, "low"), (UNDERWRITERS,)))

        members = await self._members(app.organization_id)
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
        scoring = await self._nb.scoring(application_id)
        if scoring is not None:
            signals.extend(scoring.flags)
        decision = await self._nb.decision(application_id)
        if decision is not None:
            signals.extend(decision.reason_codes)
        return signals

    async def _manual_decision_rejected(self, event: ManualDecisionRejected) -> list[Delivery]:
        app = await self._application(event.application_id)
        rendered = t.BANK_MANUAL_DECISION_REJECTED.render(number=app.number, reason=event.reason)
        entry = self._bank_entry(
            app, rendered, "high", action_required=True, link=f"/backoffice/tasks/{event.task_id}"
        )
        return [Delivery(entry, (UNDERWRITERS,))]

    async def _pre_approved(self, event: PreApprovedOffersUpdated) -> list[Delivery]:
        offers = await self._nb.pre_approved(event.organization_id)
        if not offers:
            return []
        lines = []
        for offer in offers:
            name = await self._nb.product_name(offer.product_code) or offer.product_code
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
        return [Delivery(entry, await self._members(event.organization_id), replace_group=True)]

    # --- clients.events ----------------------------------------------------------

    def _company_entry(
        self,
        organization_id: UUID,
        rendered: tuple[str, str],
        priority: Priority = "normal",
        *,
        type: FeedItemType = "status_changed",
        action_required: bool = False,
    ) -> FeedEntry:
        title, body = rendered
        return FeedEntry(
            type=type,
            audience="client",
            title=title,
            body=body,
            link=f"/organizations/{organization_id}",
            priority=priority,
            action_required=action_required,
            organization_id=organization_id,
        )

    async def _organization_verified(self, event: OrganizationVerified) -> list[Delivery]:
        name = await self._client_name(event.organization_id)
        entry = self._company_entry(
            event.organization_id, t.ORGANIZATION_VERIFIED.render(organization=name), "low"
        )
        return [Delivery(entry, await self._members(event.organization_id))]

    async def _organization_mismatch(
        self, event: OrganizationVerificationMismatch
    ) -> list[Delivery]:
        name = await self._client_name(event.organization_id)
        lines = [
            f"{t.DISCREPANCY_TITLES.get(d.field, d.field)}: в кабинете «{d.declared or '—'}», "
            f"в реестре «{d.registry or '—'}»"
            for d in event.discrepancies
        ]
        rendered = t.ORGANIZATION_MISMATCH.render(organization=name, discrepancies=t.bullets(lines))
        entry = self._company_entry(
            event.organization_id, rendered, "high", type="info_requested", action_required=True
        )
        return [Delivery(entry, await self._members(event.organization_id))]

    async def _member_added(self, event: MemberAdded) -> list[Delivery]:
        rendered = t.MEMBER_ADDED.render(
            organization=await self._client_name(event.organization_id),
            role=t.ROLE_TITLES.get(event.role, event.role),
        )
        entry = self._company_entry(event.organization_id, rendered)
        return [Delivery(entry, (Recipient.account(event.account_id),))]

    async def _member_removed(self, event: MemberRemoved) -> list[Delivery]:
        rendered = t.MEMBER_REMOVED.render(
            organization=await self._client_name(event.organization_id)
        )
        entry = self._company_entry(event.organization_id, rendered)
        return [Delivery(entry, (Recipient.account(event.account_id),))]

    async def _member_role_changed(self, event: MemberRoleChanged) -> list[Delivery]:
        rendered = t.MEMBER_ROLE_CHANGED.render(
            organization=await self._client_name(event.organization_id),
            role=t.ROLE_TITLES.get(event.role, event.role),
        )
        entry = self._company_entry(event.organization_id, rendered)
        return [Delivery(entry, (Recipient.account(event.account_id),))]

    async def _report_submitted(self, event: FinancialReportSubmitted) -> list[Delivery]:
        if event.period_quarter:
            period = f"за {event.period_quarter} квартал {event.period_year} года"
        else:
            period = f"за {event.period_year} год"
        rendered = t.REPORT_SUBMITTED.render(
            period=period, organization=await self._client_name(event.organization_id)
        )
        entry = self._company_entry(event.organization_id, rendered, "low")
        return [Delivery(entry, await self._members(event.organization_id))]
