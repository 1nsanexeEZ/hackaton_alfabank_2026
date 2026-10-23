"""decision.commands and decision.events — key: application_id
(PreApprovedOffersUpdated — organization_id)."""

from decimal import Decimal
from typing import Literal
from uuid import UUID

from src.core.messaging import topics
from src.core.messaging.contracts.applications import OfferTerms
from src.core.messaging.contracts.base import ContractModel, IntegrationMessage

Outcome = Literal["APPROVE", "COUNTER_OFFER", "REQUEST_INFO", "MANUAL_REVIEW", "REJECT"]


class RequestedInfo(ContractModel):
    fields: list[str] = []
    documents: list[str] = []
    comment: str


class ManualTerms(ContractModel):
    amount: Decimal
    term_months: int
    rate: Decimal
    conditions: list[str] = []


class CheckStopFactors(IntegrationMessage):
    """Stop factors before scoring: none — `StopFactorsPassed`, one matched — the decision
    is made right away and the reply is `DecisionMade`."""

    TYPE = "CheckStopFactors"
    TOPIC = topics.DECISION_COMMANDS

    application_id: UUID


class StopFactorsPassed(IntegrationMessage):
    TYPE = "StopFactorsPassed"
    TOPIC = topics.DECISION_EVENTS

    application_id: UUID


class MakeDecision(IntegrationMessage):
    TYPE = "MakeDecision"
    TOPIC = topics.DECISION_COMMANDS

    application_id: UUID


class RecordManualDecision(IntegrationMessage):
    TYPE = "RecordManualDecision"
    TOPIC = topics.DECISION_COMMANDS

    application_id: UUID
    task_id: UUID
    underwriter_id: UUID
    outcome: Outcome
    terms: ManualTerms | None = None
    requested_info: RequestedInfo | None = None
    comment: str


class DecisionMade(IntegrationMessage):
    TYPE = "DecisionMade"
    TOPIC = topics.DECISION_EVENTS

    application_id: UUID
    decision_id: UUID
    outcome: Outcome
    offer: OfferTerms | None = None
    decided_by: Literal["auto", "underwriter"]
    requested_info: RequestedInfo | None = None
    client_explanation: str
    improvement_hints: list[str] = []
    alternative_product_code: str | None = None


class ManualDecisionRejected(IntegrationMessage):
    TYPE = "ManualDecisionRejected"
    TOPIC = topics.DECISION_EVENTS

    application_id: UUID
    task_id: UUID
    reason: str


class PreApprovedOffersUpdated(IntegrationMessage):
    TYPE = "PreApprovedOffersUpdated"
    TOPIC = topics.DECISION_EVENTS

    organization_id: UUID
