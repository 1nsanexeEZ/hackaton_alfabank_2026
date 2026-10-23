from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, get_args, get_origin
from uuid import uuid4

import pytest
from pydantic import BaseModel, ValidationError

from src.core.messaging import topics
from src.core.messaging.contracts import CONTRACTS, IntegrationMessage, get_contract
from src.core.messaging.contracts.applications import OfferTerms
from src.core.messaging.contracts.decision import RequestedInfo
from src.core.messaging.envelope import Envelope
from src.core.messaging.outbox import build_envelope

EXPECTED = {
    "AccountRegistered",
    "OrganizationVerified",
    "OrganizationVerificationMismatch",
    "MemberAdded",
    "MemberRemoved",
    "MemberRoleChanged",
    "FinancialReportSubmitted",
    "ApplicationSubmitted",
    "ApplicationStatusChanged",
    "ApplicationInfoProvided",
    "OfferAccepted",
    "OfferDeclined",
    "OfferExpired",
    "ApplicationSigned",
    "ApplicationCancelled",
    "StartReview",
    "RequestInfo",
    "PresentOffer",
    "RejectApplication",
    "MarkDisbursed",
    "ProcessStarted",
    "StepCompleted",
    "UserTaskCreated",
    "UserTaskCompleted",
    "ProcessCompleted",
    "ProcessFailed",
    "FetchEnrichment",
    "EnrichmentCompleted",
    "EnrichmentFailed",
    "CalculateScore",
    "ScoreCalculated",
    "ScoringFailed",
    "CheckStopFactors",
    "StopFactorsPassed",
    "MakeDecision",
    "RecordManualDecision",
    "DecisionMade",
    "ManualDecisionRejected",
    "PreApprovedOffersUpdated",
}

NOW = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)


def sample(annotation: Any, name: str) -> Any:
    """Minimal valid value for a field annotation."""
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin is None and isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return build(annotation)
    if args and type(None) in args:
        return None
    if origin in (list, tuple, set, frozenset):
        return []
    if origin is dict:
        return {}
    if str(origin) == "typing.Literal":
        return args[0]
    if annotation is bool:
        return True
    if annotation is int:
        return 1
    if annotation is Decimal:
        return Decimal("1000000.50")
    if annotation is str:
        return f"{name}-value"
    if annotation is datetime:
        return NOW
    if getattr(annotation, "__name__", "") == "UUID":
        return uuid4()
    if getattr(annotation, "__name__", "") == "date":
        return NOW.date()
    raise AssertionError(f"No sample for {name}: {annotation!r}")


def build(model: type[BaseModel]) -> BaseModel:
    if model is OfferTerms:
        return OfferTerms(
            kind="counter",
            amount=Decimal("3000000"),
            term_months=24,
            rate=Decimal("23.5"),
            monthly_payment=Decimal("158000.12"),
            expires_at=NOW,
        )
    if model is RequestedInfo:
        return RequestedInfo(documents=["bank_statement"], comment="Выписка за 6 месяцев")
    values = {
        name: sample(field.annotation, name)
        for name, field in model.model_fields.items()
        if field.is_required()
    }
    return model(**values)


def test_catalog_is_complete() -> None:
    assert set(CONTRACTS) == EXPECTED


@pytest.mark.parametrize("message_type", sorted(EXPECTED))
def test_contract_round_trips_through_envelope(message_type: str) -> None:
    contract = get_contract(message_type)
    assert contract.TOPIC in topics.ALL_TOPICS
    message = build(contract)
    correlation_id = uuid4()

    envelope = build_envelope(
        message, producer="test", occurred_at=NOW, correlation_id=correlation_id
    )
    wire = Envelope.model_validate_json(envelope.model_dump_json())

    assert wire.type == message_type
    assert wire.schema_version == contract.SCHEMA_VERSION
    assert get_contract(wire.type).model_validate(wire.payload) == message


def test_contracts_are_strict() -> None:
    with pytest.raises(ValidationError):
        get_contract("MarkDisbursed").model_validate(
            {"application_id": str(uuid4()), "unexpected": 1}
        )


def test_duplicate_type_is_rejected() -> None:
    with pytest.raises(TypeError, match="Duplicate"):

        class Again(IntegrationMessage):  # noqa: F841
            TYPE = "StartReview"
            TOPIC = topics.APPLICATIONS_COMMANDS


def test_unknown_type() -> None:
    with pytest.raises(LookupError):
        get_contract("NoSuchMessage")


def test_fetch_enrichment_without_the_head_still_reads() -> None:
    """A command written before personal consents: no head, no head consent."""
    old = {
        "application_id": str(uuid4()),
        "organization_id": str(uuid4()),
        "inn": "7701158817",
        "sources": ["egrul", "fns", "bki"],
        "bki_consent_at": NOW.isoformat(),
    }

    command = get_contract("FetchEnrichment").model_validate(old)

    assert command.head is None  # type: ignore[attr-defined]
    assert command.head_bki_consent_at is None  # type: ignore[attr-defined]
