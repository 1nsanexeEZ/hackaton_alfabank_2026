"""clients.events -> entries about the company for its members."""

from uuid import UUID

from src.core.messaging.contracts.clients import (
    FinancialReportSubmitted,
    MemberAdded,
    MemberRemoved,
    MemberRoleChanged,
    OrganizationVerificationMismatch,
    OrganizationVerified,
)
from src.modules.notifications.application.deliveries.context import DeliveryContext, Handlers
from src.modules.notifications.domain import templates as t
from src.modules.notifications.domain.enums import FeedItemType, Priority
from src.modules.notifications.domain.feed import Delivery, FeedEntry, Recipient


def company_entry(
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


class ClientDeliveries:
    def __init__(self, ctx: DeliveryContext) -> None:
        self._ctx = ctx

    def handlers(self) -> Handlers:
        return {
            OrganizationVerified: self._organization_verified,
            OrganizationVerificationMismatch: self._organization_mismatch,
            MemberAdded: self._member_added,
            MemberRemoved: self._member_removed,
            MemberRoleChanged: self._member_role_changed,
            FinancialReportSubmitted: self._report_submitted,
        }

    async def _organization_verified(self, event: OrganizationVerified) -> list[Delivery]:
        name = await self._ctx.client_name(event.organization_id)
        entry = company_entry(
            event.organization_id, t.ORGANIZATION_VERIFIED.render(organization=name), "low"
        )
        return [Delivery(entry, await self._ctx.members(event.organization_id))]

    async def _organization_mismatch(
        self, event: OrganizationVerificationMismatch
    ) -> list[Delivery]:
        name = await self._ctx.client_name(event.organization_id)
        lines = [
            f"{t.DISCREPANCY_TITLES.get(d.field, d.field)}: в кабинете «{d.declared or '—'}», "
            f"в реестре «{d.registry or '—'}»"
            for d in event.discrepancies
        ]
        rendered = t.ORGANIZATION_MISMATCH.render(organization=name, discrepancies=t.bullets(lines))
        entry = company_entry(
            event.organization_id, rendered, "high", type="info_requested", action_required=True
        )
        return [Delivery(entry, await self._ctx.members(event.organization_id))]

    async def _member_added(self, event: MemberAdded) -> list[Delivery]:
        rendered = t.MEMBER_ADDED.render(
            organization=await self._ctx.client_name(event.organization_id),
            role=t.ROLE_TITLES.get(event.role, event.role),
        )
        entry = company_entry(event.organization_id, rendered)
        return [Delivery(entry, (Recipient.account(event.account_id),))]

    async def _member_removed(self, event: MemberRemoved) -> list[Delivery]:
        rendered = t.MEMBER_REMOVED.render(
            organization=await self._ctx.client_name(event.organization_id)
        )
        entry = company_entry(event.organization_id, rendered)
        return [Delivery(entry, (Recipient.account(event.account_id),))]

    async def _member_role_changed(self, event: MemberRoleChanged) -> list[Delivery]:
        rendered = t.MEMBER_ROLE_CHANGED.render(
            organization=await self._ctx.client_name(event.organization_id),
            role=t.ROLE_TITLES.get(event.role, event.role),
        )
        entry = company_entry(event.organization_id, rendered)
        return [Delivery(entry, (Recipient.account(event.account_id),))]

    async def _report_submitted(self, event: FinancialReportSubmitted) -> list[Delivery]:
        if event.period_quarter:
            period = f"за {event.period_quarter} квартал {event.period_year} года"
        else:
            period = f"за {event.period_year} год"
        rendered = t.REPORT_SUBMITTED.render(
            period=period, organization=await self._ctx.client_name(event.organization_id)
        )
        entry = company_entry(event.organization_id, rendered, "low")
        return [Delivery(entry, await self._ctx.members(event.organization_id))]
