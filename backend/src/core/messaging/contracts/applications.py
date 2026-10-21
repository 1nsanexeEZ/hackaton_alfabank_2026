"""applications.events and applications.commands — key: application_id.

Commands are sent only by the process engine; the applications module is the
only owner of the business status and decides whether a transition is allowed.
"""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from src.core.messaging import topics
from src.core.messaging.contracts.base import ContractModel, IntegrationMessage

# --- shared parts -----------------------------------------------------------


class OfferTerms(ContractModel):
    kind: Literal["as_requested", "counter"]
    amount: Decimal
    term_months: int
    rate: Decimal
    monthly_payment: Decimal
    schedule_type: Literal["annuity", "differentiated", "interest_only"] = "annuity"
    conditions: list[str] = []
    expires_at: datetime


# --- events -----------------------------------------------------------------


class ApplicationSubmitted(IntegrationMessage):
    TYPE = "ApplicationSubmitted"
    TOPIC = topics.APPLICATIONS_EVENTS

    application_id: UUID
    organization_id: UUID
    product_code: str
    amount: Decimal
    term_months: int
    purpose: str


class ApplicationStatusChanged(IntegrationMessage):
    TYPE = "ApplicationStatusChanged"
    TOPIC = topics.APPLICATIONS_EVENTS

    application_id: UUID
    organization_id: UUID
    from_status: str
    to_status: str
    client_stage: str | None = None


class ApplicationInfoProvided(IntegrationMessage):
    TYPE = "ApplicationInfoProvided"
    TOPIC = topics.APPLICATIONS_EVENTS

    application_id: UUID
    organization_id: UUID
    info_request_id: UUID
    document_ids: list[UUID] = []


class OfferAccepted(IntegrationMessage):
    TYPE = "OfferAccepted"
    TOPIC = topics.APPLICATIONS_EVENTS

    application_id: UUID
    organization_id: UUID


class OfferDeclined(IntegrationMessage):
    TYPE = "OfferDeclined"
    TOPIC = topics.APPLICATIONS_EVENTS

    application_id: UUID
    organization_id: UUID


class OfferExpired(IntegrationMessage):
    TYPE = "OfferExpired"
    TOPIC = topics.APPLICATIONS_EVENTS

    application_id: UUID
    organization_id: UUID


class ApplicationSigned(IntegrationMessage):
    TYPE = "ApplicationSigned"
    TOPIC = topics.APPLICATIONS_EVENTS

    application_id: UUID
    organization_id: UUID
    signed_by: UUID


class ApplicationCancelled(IntegrationMessage):
    TYPE = "ApplicationCancelled"
    TOPIC = topics.APPLICATIONS_EVENTS

    application_id: UUID
    organization_id: UUID


# --- commands (sent by process) ---------------------------------------------


class StartReview(IntegrationMessage):
    TYPE = "StartReview"
    TOPIC = topics.APPLICATIONS_COMMANDS

    application_id: UUID
    client_stage: str | None = None


class RequestInfo(IntegrationMessage):
    TYPE = "RequestInfo"
    TOPIC = topics.APPLICATIONS_COMMANDS

    application_id: UUID
    requested_fields: list[str] = []
    requested_documents: list[str] = []
    comment: str
    due_at: datetime | None = None


class PresentOffer(IntegrationMessage):
    TYPE = "PresentOffer"
    TOPIC = topics.APPLICATIONS_COMMANDS

    application_id: UUID
    decision_id: UUID
    offer: OfferTerms
    client_explanation: str
    improvement_hints: list[str] = []
    alternative_product_code: str | None = None


class RejectApplication(IntegrationMessage):
    TYPE = "RejectApplication"
    TOPIC = topics.APPLICATIONS_COMMANDS

    application_id: UUID
    decision_id: UUID | None = None
    client_explanation: str
    improvement_hints: list[str] = []
    alternative_product_code: str | None = None


class MarkDisbursed(IntegrationMessage):
    TYPE = "MarkDisbursed"
    TOPIC = topics.APPLICATIONS_COMMANDS

    application_id: UUID
