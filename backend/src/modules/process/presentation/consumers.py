"""Kafka entry points of the engine.

One consumer group per topic (`process.<topic>`): applications events start,
move and cancel processes; replies of enrichment, scoring and decision are
matched to the command by `causation_id`.
"""

from typing import Any

from src.core.messaging import topics
from src.core.messaging.contracts import applications as app_events
from src.core.messaging.contracts.base import IntegrationMessage
from src.core.messaging.subscriber import HandlerContext, Subscription
from src.modules.process.application.mappers.messages import trigger
from src.modules.process.presentation.dependencies import (
    cancel_process_use_case,
    handle_trigger_use_case,
    start_process_use_case,
)

MODULE = "process"

CLIENT_EVENTS = frozenset(
    {
        app_events.ApplicationInfoProvided.TYPE,
        app_events.OfferAccepted.TYPE,
        app_events.OfferDeclined.TYPE,
        app_events.OfferExpired.TYPE,
        app_events.ApplicationSigned.TYPE,
    }
)
REPLIES = {
    topics.ENRICHMENT_EVENTS: frozenset({"EnrichmentCompleted", "EnrichmentFailed"}),
    topics.SCORING_EVENTS: frozenset({"ScoreCalculated", "ScoringFailed"}),
    topics.DECISION_EVENTS: frozenset({"DecisionMade", "ManualDecisionRejected"}),
}


async def handle_application_event(ctx: HandlerContext, event: IntegrationMessage) -> None:
    payload: Any = event
    causation = ctx.envelope.event_id
    if isinstance(event, app_events.ApplicationSubmitted):
        await start_process_use_case(ctx).execute(
            event.application_id, event.organization_id, event.product_code, causation
        )
    elif isinstance(event, app_events.ApplicationCancelled):
        await cancel_process_use_case(ctx).execute(event.application_id, causation)
    else:
        await handle_trigger_use_case(ctx).execute(
            payload.application_id, trigger(event), causation
        )


async def handle_reply(ctx: HandlerContext, reply: IntegrationMessage) -> None:
    application_id = reply.application_id  # type: ignore[attr-defined]
    await handle_trigger_use_case(ctx).execute(
        application_id, trigger(reply, ctx.envelope.causation_id), ctx.envelope.event_id
    )


def subscriptions() -> list[Subscription]:
    started_by = {app_events.ApplicationSubmitted.TYPE, app_events.ApplicationCancelled.TYPE}
    return [
        Subscription(
            MODULE,
            topics.APPLICATIONS_EVENTS,
            "process.applications-events",
            handle_application_event,
            message_types=frozenset(started_by | CLIENT_EVENTS),
        ),
        *(
            Subscription(MODULE, topic, f"process.{topic.replace('.', '-')}", handle_reply, types)
            for topic, types in REPLIES.items()
        ),
    ]
