"""Kafka entry points of clients."""

import logging

from src.core.exceptions.exceptions import InfrastructureError
from src.core.messaging import topics
from src.core.messaging.contracts.enrichment import EnrichmentCompleted
from src.core.messaging.subscriber import HandlerContext, Subscription
from src.core.uow import SqlAlchemyUnitOfWork
from src.modules.clients.application.verification import VerifyOrganizationUseCase
from src.modules.clients.infrastructure.registry import EnrichmentRegistryLookup, extract_of
from src.modules.clients.infrastructure.repositories import SqlAlchemyOrganizationRepository
from src.modules.enrichment.facade import EnrichmentFacade
from src.modules.identity.facade import IdentityFacade

logger = logging.getLogger(__name__)

MODULE = "clients"


async def handle_enrichment_completed(ctx: HandlerContext, event: EnrichmentCompleted) -> None:
    """Auto check: every application brings a fresh ЕГРЮЛ extract, and the
    company follows it with no extra request to the registry. A snapshot
    without the extract (the source failed) is skipped."""
    enrichment = ctx.facade(EnrichmentFacade)
    snapshot = await enrichment.get_snapshot(event.application_id)
    if snapshot is None or snapshot.egrul is None:
        return
    try:
        extract = extract_of(snapshot.egrul)
    except InfrastructureError:
        logger.warning("Unreadable registry extract, check skipped: %s", event.application_id)
        return
    use_case = VerifyOrganizationUseCase(
        SqlAlchemyUnitOfWork(ctx.session),
        SqlAlchemyOrganizationRepository(ctx.session),
        ctx.outbox,
        ctx.clock,
        EnrichmentRegistryLookup(enrichment),
        ctx.facade(IdentityFacade),
    )
    await use_case.apply_extract(
        snapshot.organization_id,
        extract,
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
