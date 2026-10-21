"""clients.events — key: organization_id."""

from uuid import UUID

from src.core.messaging import topics
from src.core.messaging.contracts.base import ContractModel, IntegrationMessage


class Discrepancy(ContractModel):
    field: str
    declared: str | None = None
    registry: str | None = None


class OrganizationVerified(IntegrationMessage):
    TYPE = "OrganizationVerified"
    TOPIC = topics.CLIENTS_EVENTS

    organization_id: UUID


class OrganizationVerificationMismatch(IntegrationMessage):
    TYPE = "OrganizationVerificationMismatch"
    TOPIC = topics.CLIENTS_EVENTS

    organization_id: UUID
    discrepancies: list[Discrepancy]


class MemberAdded(IntegrationMessage):
    TYPE = "MemberAdded"
    TOPIC = topics.CLIENTS_EVENTS

    organization_id: UUID
    account_id: UUID
    role: str


class MemberRemoved(IntegrationMessage):
    TYPE = "MemberRemoved"
    TOPIC = topics.CLIENTS_EVENTS

    organization_id: UUID
    account_id: UUID


class MemberRoleChanged(IntegrationMessage):
    TYPE = "MemberRoleChanged"
    TOPIC = topics.CLIENTS_EVENTS

    organization_id: UUID
    account_id: UUID
    role: str


class FinancialReportSubmitted(IntegrationMessage):
    TYPE = "FinancialReportSubmitted"
    TOPIC = topics.CLIENTS_EVENTS

    organization_id: UUID
    period_year: int
    period_quarter: int | None = None
