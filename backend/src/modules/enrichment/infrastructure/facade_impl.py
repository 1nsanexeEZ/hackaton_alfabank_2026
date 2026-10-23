from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions.exceptions import InfrastructureError
from src.modules.enrichment.application.ports import (
    PersonBureauSource,
    PersonQuery,
    RegistrySource,
    SourceNotFound,
    SourceUnavailable,
)
from src.modules.enrichment.domain.snapshot import EnrichmentSnapshot
from src.modules.enrichment.facade import (
    CreditHistoryDTO,
    EnrichmentSnapshotDTO,
    PersonDTO,
    RegistryExtractDTO,
    Source,
    SourceErrorDTO,
)
from src.modules.enrichment.infrastructure.repository import SqlAlchemyEnrichmentRepository

_LOOKUP_TTL = timedelta(minutes=10)
_lookup_cache: dict[str, tuple[datetime, RegistryExtractDTO]] = {}


class EnrichmentFacadeImpl:
    """Чтение снимка для соседей (scoring, decision, bff), разовый просмотр реестра по ИНН и
    кредитной истории физлица (предскрин учредителя)."""

    def __init__(
        self,
        session: AsyncSession,
        registry: RegistrySource,
        person_bureau: PersonBureauSource | None = None,
    ) -> None:
        self._repo = SqlAlchemyEnrichmentRepository(session)
        self._registry = registry
        self._person_bureau = person_bureau

    async def get_snapshot(self, application_id: UUID) -> EnrichmentSnapshotDTO | None:
        snapshot = await self._repo.latest_for_application(application_id)
        if snapshot is None:
            return None
        # sources_failed исключает внутренний `statement` (как и sources_ok) — симметрично
        # с домено́вым снимком; провал разбора выписки виден по cashflow=None, не как источник.
        failed = _errors(snapshot, snapshot.sources_failed)
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
            gir_bo=snapshot.accounting(),
            kontur=snapshot.counterparty(),
            bki_head=snapshot.head_credit_history(),
            sources_skipped=_errors(snapshot, snapshot.sources_skipped),
        )

    async def lookup_registry(self, inn: str, *, fresh: bool = False) -> RegistryExtractDTO | None:
        now = datetime.now(UTC)
        cached = _lookup_cache.get(inn)
        if not fresh and cached is not None and cached[0] > now:
            return cached[1]
        try:
            extract = await self._registry.fetch(inn)
        except SourceNotFound:
            return None
        except SourceUnavailable as exc:
            raise InfrastructureError("Реестр временно недоступен") from exc
        _lookup_cache[inn] = (now + _LOOKUP_TTL, extract)
        return extract

    async def lookup_person_bureau(
        self, person: PersonDTO, consent_at: datetime
    ) -> CreditHistoryDTO | None:
        """Без кеша: согласие и ответ бюро — на момент запроса."""
        if self._person_bureau is None:
            raise InfrastructureError("БКИ физлиц не подключено")
        query = PersonQuery(
            last_name=person.last_name,
            first_name=person.first_name,
            middle_name=person.middle_name,
            company_inn=person.company_inn,
        )
        try:
            return await self._person_bureau.fetch(query, consent_at)
        except SourceNotFound:
            return None
        except SourceUnavailable as exc:
            raise InfrastructureError("Бюро кредитных историй временно недоступно") from exc


def _errors(snapshot: EnrichmentSnapshot, sources: list[Source]) -> tuple[SourceErrorDTO, ...]:
    return tuple(
        SourceErrorDTO(source=source, code=error.kind, message=error.message)
        for source in sources
        if (error := snapshot.results[source].error) is not None
    )
