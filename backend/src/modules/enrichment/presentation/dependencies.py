"""Сборка use case'ов и фасада из реализаций infrastructure."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.messaging.subscriber import HandlerContext
from src.modules.applications.facade import ApplicationsFacade
from src.modules.enrichment.application.interfaces.registry_cache import RegistryCache
from src.modules.enrichment.application.interfaces.sources import Sources
from src.modules.enrichment.application.use_cases.build_cashflow import CashflowBuilder
from src.modules.enrichment.application.use_cases.fetch_enrichment import FetchEnrichmentUseCase
from src.modules.enrichment.application.use_cases.get_snapshot import GetSnapshotUseCase
from src.modules.enrichment.application.use_cases.latest_cashflow import GetLatestCashflowUseCase
from src.modules.enrichment.application.use_cases.lookup_person_bureau import (
    LookupPersonBureauUseCase,
)
from src.modules.enrichment.application.use_cases.lookup_registry import LookupRegistryUseCase
from src.modules.enrichment.infrastructure.adapters.enrichment_facade import EnrichmentFacadeImpl
from src.modules.enrichment.infrastructure.adapters.statement_csv import CsvStatementParser
from src.modules.enrichment.infrastructure.repositories.enrichment_repository import (
    SqlAlchemyEnrichmentRepository,
)


def enrichment_facade(
    session: AsyncSession, sources: Sources, registry_cache: RegistryCache
) -> EnrichmentFacadeImpl:
    repository = SqlAlchemyEnrichmentRepository(session)
    return EnrichmentFacadeImpl(
        GetSnapshotUseCase(repository),
        LookupRegistryUseCase(sources.registry, registry_cache),
        LookupPersonBureauUseCase(sources.person_bureau),
        GetLatestCashflowUseCase(repository),
    )


def fetch_enrichment_use_case(ctx: HandlerContext, sources: Sources) -> FetchEnrichmentUseCase:
    return FetchEnrichmentUseCase(
        SqlAlchemyEnrichmentRepository(ctx.session),
        sources,
        ctx.clock,
        CashflowBuilder(ctx.facade(ApplicationsFacade), CsvStatementParser()),  # type: ignore[type-abstract]
    )
