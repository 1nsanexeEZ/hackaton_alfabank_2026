"""Kafka entry points of clients."""

from src.core.messaging import topics
from src.core.messaging.contracts.enrichment import EnrichmentCompleted
from src.core.messaging.subscriber import HandlerContext, Subscription
from src.modules.clients.presentation.dependencies import apply_registry_extract_use_case

MODULE = "clients"


async def handle_enrichment_completed(ctx: HandlerContext, event: EnrichmentCompleted) -> None:
    """Auto check: the company follows the ЕГРЮЛ extract of the application."""
    await apply_registry_extract_use_case(ctx).execute(
        event.application_id,
        correlation_id=ctx.envelope.correlation_id,
        causation_id=ctx.envelope.event_id,
    )


def subscriptions() -> list[Subscription]:
    return [
        Subscription(
            MODULE,
            topics.ENRICHMENT_EVENTS,
            "clients.enrichment-events",
            handle_enrichment_completed,
            message_types=frozenset({EnrichmentCompleted.TYPE}),
        )
    ]
