"""Kafka side of the feed: one subscription per source topic. The handler does
not commit — the processor commits the records together with the inbox mark."""

from src.core.messaging import topics
from src.core.messaging.contracts.base import IntegrationMessage
from src.core.messaging.subscriber import HandlerContext, Subscription
from src.modules.notifications.application.use_cases.project_event import handled_types
from src.modules.notifications.presentation.dependencies import project_event_use_case

MODULE = "notifications"
SOURCE_TOPICS: tuple[str, ...] = (
    topics.APPLICATIONS_EVENTS,
    topics.PROCESS_EVENTS,
    topics.DECISION_EVENTS,
    topics.CLIENTS_EVENTS,
)


def group_id(topic: str) -> str:
    """Consumer groups are unique per subscription: `notifications.feed.<source>`."""
    return f"{MODULE}.feed.{topic.split('.')[0]}"


async def handle_event(ctx: HandlerContext, message: IntegrationMessage) -> None:
    await project_event_use_case(ctx).execute(message, ctx.envelope.event_id, ctx.clock.now())


def feed_subscriptions() -> list[Subscription]:
    return [
        Subscription(
            module=MODULE,
            topic=topic,
            group_id=group_id(topic),
            handler=handle_event,
            message_types=handled_types(topic),
        )
        for topic in SOURCE_TOPICS
    ]
