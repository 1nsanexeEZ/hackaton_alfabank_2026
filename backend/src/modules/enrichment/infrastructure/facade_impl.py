from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions.exceptions import InfrastructureError
from src.modules.enrichment.application.ports import (
    RegistrySource,
    SourceNotFound,
    SourceUnavailable,
)
from src.modules.enrichment.facade import EnrichmentSnapshotDTO, RegistryExtractDTO, SourceErrorDTO
from src.modules.enrichment.infrastructure.repository import SqlAlchemyEnrichmentRepository

_LOOKUP_TTL = timedelta(minutes=10)
_lookup_cache: dict[str, tuple[datetime, RegistryExtractDTO]] = {}


class EnrichmentFacadeImpl:
    """Чтение снимка для соседей (scoring, decision, bff) и разовый просмотр реестра по ИНН."""

    def __init__(self, session: AsyncSession, registry: RegistrySource) -> None:
        self._repo = SqlAlchemyEnrichmentRepository(session)
        self._registry = registry

    async def get_snapshot(self, application_id: UUID) -> EnrichmentSnapshotDTO | None:
        snapshot = await self._repo.latest_for_application(application_id)
        if snapshot is None:
            return None
        # sources_failed исключает внутренний `statement` (как и sources_ok) — симметрично
        # с домено́вым снимком; провал разбора выписки виден по cashflow=None, не как источник.
        failed = tuple(
            SourceErrorDTO(
                source=source,
                code=snapshot.results[source].error.kind,
                message=snapshot.results[source].error.message,
            )
            for source in snapshot.sources_failed
            if snapshot.results[source].error is not None
        )
        return EnrichmentSnapshotDTO(
            id=snapshot.id,
            application_id=snapshot.application_id,
            organization_id=snapshot.organization_id,
            collected_at=snapshot.completed_at or snapshot.started_at,
            sources_ok=tuple(snapshot.sources_ok),
            sources_failed=failed,
            egrul=snapshot.registry(),
            fns=snapshot.tax(),
            bki=snapshot.credit_history(),
            cashflow=snapshot.cashflow(),
        )

    async def lookup_registry(self, inn: str) -> RegistryExtractDTO | None:
        now = datetime.now(UTC)
        cached = _lookup_cache.get(inn)
        if cached is not None and cached[0] > now:
            return cached[1]
        try:
            extract = await self._registry.fetch(inn)
        except SourceNotFound:
            return None
        except SourceUnavailable as exc:
            raise InfrastructureError("Реестр временно недоступен") from exc
        _lookup_cache[inn] = (now + _LOOKUP_TTL, extract)
        return extract
