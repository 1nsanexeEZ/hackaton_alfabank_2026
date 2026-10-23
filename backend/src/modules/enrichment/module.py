"""Wiring of the enrichment module into the application."""

from __future__ import annotations

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.messaging import topics
from src.core.messaging.contracts.enrichment import FetchEnrichment
from src.core.messaging.subscriber import HandlerContext, Subscription
from src.modules.applications.facade import ApplicationsFacade
from src.modules.enrichment.application.cashflow import CashflowBuilder
from src.modules.enrichment.application.fetch_enrichment import FetchEnrichmentUseCase
from src.modules.enrichment.application.sources import Sources
from src.modules.enrichment.config import EnrichmentSettings
from src.modules.enrichment.facade import EnrichmentFacade
from src.modules.enrichment.infrastructure.facade_impl import EnrichmentFacadeImpl
from src.modules.enrichment.infrastructure.repository import SqlAlchemyEnrichmentRepository
from src.modules.enrichment.infrastructure.sources import build_http_sources

NAME = "enrichment"

# HTTP sources live for the process; built in wire(), used by the Kafka handler.
_sources: Sources | None = None


def register(app: FastAPI) -> None:
    """Enrichment has no public HTTP API — only a facade and a command handler."""


def wire(app: FastAPI) -> None:
    global _sources
    _sources = build_http_sources(EnrichmentSettings())
    app.state.facades.register(EnrichmentFacade, _facade)


def _facade(session: AsyncSession) -> EnrichmentFacadeImpl:
    """Sources are read at the call: the same ones the command handler uses."""
    if _sources is None:
        raise RuntimeError("enrichment module is not wired")
    return EnrichmentFacadeImpl(session, _sources.registry, _sources.person_bureau)


async def _on_fetch_enrichment(ctx: HandlerContext, payload: FetchEnrichment) -> None:
    if _sources is None:
        raise RuntimeError("enrichment module is not wired")
    use_case = FetchEnrichmentUseCase(
        SqlAlchemyEnrichmentRepository(ctx.session),
        _sources,
        ctx.clock,
        CashflowBuilder(ctx.facade(ApplicationsFacade)),
    )
    await use_case.execute(payload, command_event_id=ctx.envelope.event_id, outbox=ctx.outbox)


def subscribers() -> list[Subscription]:
    return [
        Subscription(
            module=NAME,
            topic=topics.ENRICHMENT_COMMANDS,
            group_id="enrichment.commands",
            handler=_on_fetch_enrichment,
            message_types=frozenset({FetchEnrichment.TYPE}),
        )
    ]
