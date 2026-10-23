"""Kafka subscriptions of the projector: every event of the four topics goes
through the same ProjectEventUseCase as the rebuild."""

from src.core.messaging import topics
from src.core.messaging.contracts.base import IntegrationMessage
from src.core.messaging.subscriber import HandlerContext, Subscription
from src.modules.projector.presentation.dependencies import project_event_use_case

MODULE = "projector"
GROUP_PREFIX = "projector.read-models"

# topic -> suffix of its consumer group: a group reads one topic (core rule).
PROJECTED_TOPICS: dict[str, str] = {
    topics.APPLICATIONS_EVENTS: "applications",
    topics.PROCESS_EVENTS: "process",
    topics.DECISION_EVENTS: "decision",
    topics.CLIENTS_EVENTS: "clients",
}


def group_id(topic: str, prefix: str = GROUP_PREFIX) -> str:
    return f"{prefix}.{PROJECTED_TOPICS[topic]}"


async def project(ctx: HandlerContext, message: IntegrationMessage) -> None:
    await project_event_use_case(ctx).execute(ctx.envelope, message)


def subscriptions(prefix: str = GROUP_PREFIX) -> list[Subscription]:
    return [
        Subscription(module=MODULE, topic=topic, group_id=group_id(topic, prefix), handler=project)
        for topic in PROJECTED_TOPICS
    ]
