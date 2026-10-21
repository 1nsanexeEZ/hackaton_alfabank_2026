"""Domain events → `clients.events` contracts, staged in the outbox in the
transaction of the change. Key — organization_id."""

from collections.abc import Iterable
from uuid import UUID

from src.clients.application.ports import EventOutbox
from src.clients.domain import events as domain
from src.core.messaging.contracts import clients as contracts
from src.core.messaging.contracts.base import IntegrationMessage

PRODUCER = "clients"


def to_contract(event: domain.OrganizationEvent) -> IntegrationMessage:
    match event:
        case domain.MemberAdded():
            return contracts.MemberAdded(
                organization_id=event.organization_id, account_id=event.account_id, role=event.role
            )
        case domain.MemberRemoved():
            return contracts.MemberRemoved(
                organization_id=event.organization_id, account_id=event.account_id
            )
        case domain.MemberRoleChanged():
            return contracts.MemberRoleChanged(
                organization_id=event.organization_id, account_id=event.account_id, role=event.role
            )
        case domain.FinancialReportSubmitted():
            return contracts.FinancialReportSubmitted(
                organization_id=event.organization_id,
                period_year=event.period_year,
                period_quarter=event.period_quarter,
            )
        case domain.OrganizationVerified():
            return contracts.OrganizationVerified(organization_id=event.organization_id)
        case domain.OrganizationVerificationMismatch():
            return contracts.OrganizationVerificationMismatch(
                organization_id=event.organization_id,
                discrepancies=[
                    contracts.Discrepancy(field=d.field, declared=d.declared, registry=d.registry)
                    for d in event.discrepancies
                ],
            )
    raise TypeError(f"No contract for {type(event).__name__}")


async def stage(
    outbox: EventOutbox, events: Iterable[domain.OrganizationEvent], correlation_id: UUID
) -> None:
    for event in events:
        await outbox.add(
            to_contract(event), key=event.organization_id, correlation_id=correlation_id
        )
