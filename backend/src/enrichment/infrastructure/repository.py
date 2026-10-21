from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.enrichment.domain.snapshot import EnrichmentSnapshot
from src.enrichment.infrastructure.mappers import to_domain, to_records
from src.enrichment.infrastructure.models import EnrichmentSnapshotRecord, SourceResultRecord


class SqlAlchemyEnrichmentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, snapshot: EnrichmentSnapshot) -> None:
        head, results = to_records(snapshot)
        self._session.add(head)
        self._session.add_all(results)
        await self._session.flush()

    async def get_by_command(self, command_event_id: UUID) -> EnrichmentSnapshot | None:
        stmt = select(EnrichmentSnapshotRecord).where(
            EnrichmentSnapshotRecord.requested_by_command == command_event_id
        )
        head = (await self._session.scalars(stmt)).one_or_none()
        return await self._load(head) if head is not None else None

    async def latest_for_application(self, application_id: UUID) -> EnrichmentSnapshot | None:
        stmt = (
            select(EnrichmentSnapshotRecord)
            .where(EnrichmentSnapshotRecord.application_id == application_id)
            .order_by(EnrichmentSnapshotRecord.started_at.desc(), EnrichmentSnapshotRecord.id)
        )
        head = (await self._session.scalars(stmt)).first()
        return await self._load(head) if head is not None else None

    async def _load(self, head: EnrichmentSnapshotRecord) -> EnrichmentSnapshot:
        stmt = select(SourceResultRecord).where(SourceResultRecord.snapshot_id == head.id)
        results = (await self._session.scalars(stmt)).all()
        return to_domain(head, list(results))
