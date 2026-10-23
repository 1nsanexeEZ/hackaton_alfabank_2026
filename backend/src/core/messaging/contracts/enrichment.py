"""enrichment.commands and enrichment.events — key: application_id."""

from datetime import datetime
from uuid import UUID

from src.core.messaging import topics
from src.core.messaging.contracts.base import ContractModel, IntegrationMessage


class PersonRef(ContractModel):
    """A person the bank checks on their own consent (the head of the company)."""

    account_id: UUID
    last_name: str
    first_name: str
    middle_name: str | None = None


class FetchEnrichment(IntegrationMessage):
    TYPE = "FetchEnrichment"
    TOPIC = topics.ENRICHMENT_COMMANDS

    application_id: UUID
    organization_id: UUID
    inn: str
    # statement — прогноз по выпискам из statement_document_ids; bki_head — БКИ руководителя;
    # aml — проверка по 115-FZ (beneficial owners, Rosfinmonitoring lists, PEP, the KYC platform);
    # bank_stop_list — the bank's own stop list (core banking system), no consent needed.
    sources: list[str] = [
        "egrul",
        "fns",
        "bki",
        "statement",
        "gir_bo",
        "kontur",
        "bki_head",
        "aml",
        "bank_stop_list",
    ]
    # Without the consent the credit bureau is not requested at all (218-FZ).
    bki_consent_at: datetime | None = None
    # Uploaded bank statements (CSV) for the cash flow forecast.
    statement_document_ids: list[UUID] = []
    # The head by the registry and the moment of their own consent to request their
    # credit history (218-FZ): the company's consent does not cover a person.
    head: PersonRef | None = None
    head_bki_consent_at: datetime | None = None
    # Who acts for the client (submitted the application), when not the head: screened
    # against the lists and the PEP base as a representative (115-FZ).
    representative: PersonRef | None = None


class EnrichmentCompleted(IntegrationMessage):
    TYPE = "EnrichmentCompleted"
    TOPIC = topics.ENRICHMENT_EVENTS

    application_id: UUID
    snapshot_id: UUID
    sources_ok: list[str] = []
    sources_failed: list[str] = []
    cash_gap_detected: bool | None = None


class EnrichmentFailed(IntegrationMessage):
    TYPE = "EnrichmentFailed"
    TOPIC = topics.ENRICHMENT_EVENTS

    application_id: UUID
    reason: str
