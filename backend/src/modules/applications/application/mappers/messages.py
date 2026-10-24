"""Domain events -> integration contracts, process commands -> domain objects."""

from src.core.domain import Money
from src.core.messaging.contracts import applications as contracts
from src.core.messaging.contracts.base import IntegrationMessage
from src.modules.applications.domain.events import (
    ApplicationCancelled,
    ApplicationEvent,
    ApplicationInfoProvided,
    ApplicationSigned,
    ApplicationStatusChanged,
    ApplicationSubmitted,
    OfferAccepted,
    OfferDeclined,
    OfferExpired,
)
from src.modules.applications.domain.value_objects import DecisionSummary, Offer

# The producer name in the outbox.
PRODUCER = "applications"


def to_contract(event: ApplicationEvent) -> IntegrationMessage:
    ids = {"application_id": event.application_id, "organization_id": event.organization_id}
    match event:
        case ApplicationSubmitted():
            return contracts.ApplicationSubmitted(
                **ids,
                product_code=event.product_code,
                amount=event.amount.amount,
                term_months=event.term_months,
                purpose=event.purpose,
            )
        case ApplicationStatusChanged():
            return contracts.ApplicationStatusChanged(
                **ids,
                from_status=event.from_status,
                to_status=event.to_status,
                client_stage=event.client_stage,
            )
        case ApplicationInfoProvided():
            return contracts.ApplicationInfoProvided(
                **ids, info_request_id=event.info_request_id, document_ids=list(event.document_ids)
            )
        case OfferAccepted():
            return contracts.OfferAccepted(**ids)
        case OfferDeclined():
            return contracts.OfferDeclined(**ids)
        case OfferExpired():
            return contracts.OfferExpired(**ids)
        case ApplicationSigned():
            return contracts.ApplicationSigned(**ids, signed_by=event.signed_by)
        case ApplicationCancelled():
            return contracts.ApplicationCancelled(**ids)
    raise TypeError(f"No integration contract for {type(event).__name__}")


def offer_of(command: contracts.PresentOffer) -> Offer:
    terms = command.offer
    return Offer(
        kind=terms.kind,
        amount=Money.of(terms.amount),
        term_months=terms.term_months,
        rate=terms.rate,
        monthly_payment=Money.of(terms.monthly_payment),
        schedule_type=terms.schedule_type,
        conditions=tuple(terms.conditions),
        expires_at=terms.expires_at,
        decision_id=command.decision_id,
    )


def decision_of(
    command: contracts.PresentOffer | contracts.RejectApplication, outcome: str
) -> DecisionSummary:
    return DecisionSummary(
        outcome=outcome,
        client_explanation=command.client_explanation,
        improvement_hints=tuple(command.improvement_hints),
        alternative_product_code=command.alternative_product_code,
        decided_by=command.decided_by,
    )
