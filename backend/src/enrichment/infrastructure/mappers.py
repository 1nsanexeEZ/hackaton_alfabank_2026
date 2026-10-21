from __future__ import annotations

from collections.abc import Sequence
from typing import cast

from src.enrichment.domain.snapshot import (
    EnrichmentSnapshot,
    SourceError,
    SourceResult,
    SourceStatus,
)
from src.enrichment.facade import Source
from src.enrichment.infrastructure.models import EnrichmentSnapshotRecord, SourceResultRecord
from src.enrichment.infrastructure.serialization import data_from_json, data_to_json


def to_records(
    snapshot: EnrichmentSnapshot,
) -> tuple[EnrichmentSnapshotRecord, list[SourceResultRecord]]:
    head = EnrichmentSnapshotRecord(
        id=snapshot.id,
        application_id=snapshot.application_id,
        organization_id=snapshot.organization_id,
        inn=snapshot.inn,
        requested_by_command=snapshot.requested_by_command,
        requested_sources=list(snapshot.requested_sources),
        started_at=snapshot.started_at,
        completed_at=snapshot.completed_at,
    )
    results = [
        SourceResultRecord(
            snapshot_id=snapshot.id,
            source=result.source,
            status=result.status,
            fetched_at=result.fetched_at,
            latency_ms=result.latency_ms,
            attempts=result.attempts,
            data=data_to_json(result.source, result.data) if result.data is not None else None,
            error_kind=result.error.kind if result.error is not None else None,
            error_message=result.error.message if result.error is not None else None,
        )
        for result in snapshot.results.values()
    ]
    return head, results


def to_domain(
    head: EnrichmentSnapshotRecord, results: Sequence[SourceResultRecord]
) -> EnrichmentSnapshot:
    snapshot = EnrichmentSnapshot(
        id=head.id,
        application_id=head.application_id,
        organization_id=head.organization_id,
        inn=head.inn,
        requested_by_command=head.requested_by_command,
        requested_sources=tuple(cast(list[Source], head.requested_sources)),
        started_at=head.started_at,
        completed_at=head.completed_at,
    )
    for record in results:
        source = cast(Source, record.source)
        snapshot.results[source] = SourceResult(
            source=source,
            status=cast(SourceStatus, record.status),
            fetched_at=record.fetched_at,
            latency_ms=record.latency_ms,
            attempts=record.attempts,
            data=data_from_json(source, record.data) if record.data is not None else None,
            error=SourceError(record.error_kind, record.error_message or "")
            if record.error_kind is not None
            else None,
        )
    return snapshot
