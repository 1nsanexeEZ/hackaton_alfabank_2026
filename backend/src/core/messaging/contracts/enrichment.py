"""enrichment.commands and enrichment.events — key: application_id."""

from datetime import datetime
from uuid import UUID

from src.core.messaging import topics
from src.core.messaging.contracts.base import IntegrationMessage


class FetchEnrichment(IntegrationMessage):
    TYPE = "FetchEnrichment"
    TOPIC = topics.ENRICHMENT_COMMANDS

    application_id: UUID
    organization_id: UUID
    inn: str
    sources: list[str] = ["egrul", "fns", "bki"]
    # Without the consent the credit bureau is not requested at all (218-FZ).
    bki_consent_at: datetime | None = None
    # Uploaded bank statements (CSV) for the cash flow forecast.
    statement_document_ids: list[UUID] = []


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
