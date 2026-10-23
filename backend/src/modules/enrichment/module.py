"""Wiring of the enrichment module into the application."""

from __future__ import annotations

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.messaging import topics
from src.core.messaging.contracts.enrichment import FetchEnrichment
from src.core.messaging.subscriber import HandlerContext, Subscription
from src.modules.enrichment.application.interfaces.sources import Sources
from src.modules.enrichment.facade import EnrichmentFacade
from src.modules.enrichment.infrastructure.adapters.enrichment_facade import EnrichmentFacadeImpl
from src.modules.enrichment.infrastructure.adapters.http_sources import build_http_sources
from src.modules.enrichment.infrastructure.adapters.registry_cache import InMemoryRegistryCache
from src.modules.enrichment.infrastructure.config import EnrichmentSettings
from src.modules.enrichment.presentation.consumers import on_fetch_enrichment
from src.modules.enrichment.presentation.dependencies import enrichment_facade

NAME = "enrichment"

# HTTP sources live for the process; built in wire(), used by the Kafka handler.
_sources: Sources | None = None
# Registry lookups are cached for the process, across sessions.
_registry_cache = InMemoryRegistryCache()


def register(app: FastAPI) -> None:
    """Enrichment has no public HTTP API — only a facade and a command handler."""


def wire(app: FastAPI) -> None:
    global _sources
    _sources = build_http_sources(EnrichmentSettings())
    app.state.facades.register(EnrichmentFacade, _facade)


def _facade(session: AsyncSession) -> EnrichmentFacadeImpl:
    """Sources are read at the call: the same ones the command handler uses."""
    return enrichment_facade(session, _wired_sources(), _registry_cache)


async def _on_fetch_enrichment(ctx: HandlerContext, payload: FetchEnrichment) -> None:
    await on_fetch_enrichment(ctx, payload, _wired_sources())


def _wired_sources() -> Sources:
    if _sources is None:
        raise RuntimeError("enrichment module is not wired")
    return _sources


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
