"""Обработчики команд из Kafka."""

from __future__ import annotations

from src.core.messaging.contracts.enrichment import FetchEnrichment
from src.core.messaging.subscriber import HandlerContext
from src.modules.enrichment.application.interfaces.sources import Sources
from src.modules.enrichment.presentation.dependencies import fetch_enrichment_use_case


async def on_fetch_enrichment(
    ctx: HandlerContext, payload: FetchEnrichment, sources: Sources
) -> None:
    use_case = fetch_enrichment_use_case(ctx, sources)
    await use_case.execute(payload, command_event_id=ctx.envelope.event_id, outbox=ctx.outbox)
