"""Kafka subscriptions of the projector: every event of the four topics goes
through the same ReadModelProjector.apply() as the rebuild."""

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.facades import FacadeRegistry
from src.core.messaging import topics
from src.core.messaging.contracts.base import IntegrationMessage
from src.core.messaging.subscriber import HandlerContext, Subscription
from src.projector.application.projection import ReadModelProjector
from src.projector.infrastructure.repositories import SqlAlchemyReadModelStore

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


class SessionFacades:
    """Facades bound to one session, for code that runs outside a HandlerContext."""

    def __init__(self, registry: FacadeRegistry, session: AsyncSession) -> None:
        self._registry = registry
        self._session = session

    def __call__[T](self, key: type[T]) -> T:
        return self._registry.get(key, self._session)


def projector_for(session: AsyncSession, facades: FacadeRegistry) -> ReadModelProjector:
    return ReadModelProjector(SqlAlchemyReadModelStore(session), SessionFacades(facades, session))


async def project(ctx: HandlerContext, message: IntegrationMessage) -> None:
    projector = ReadModelProjector(SqlAlchemyReadModelStore(ctx.session), ctx.facade)
    await projector.apply(ctx.envelope, message)


def subscriptions(prefix: str = GROUP_PREFIX) -> list[Subscription]:
    return [
        Subscription(module=MODULE, topic=topic, group_id=group_id(topic, prefix), handler=project)
        for topic in PROJECTED_TOPICS
    ]
