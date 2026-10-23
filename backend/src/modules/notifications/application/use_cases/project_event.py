"""Business events -> feed records.

Every handled event becomes zero or more Deliveries: an entry (rendered text,
type, priority) and its recipients — the members of the company
(`ClientsFacade.list_members`) or the back office role. The rules live in
`application/deliveries`, one file per source topic.

The live consumer runs it in the handler's transaction: the use case does not
commit, the core commits the records together with the inbox mark.
"""

from datetime import datetime
from uuid import UUID

from src.core.messaging.contracts.applications import (
    ApplicationCancelled,
    ApplicationInfoProvided,
    ApplicationSigned,
    ApplicationStatusChanged,
    ApplicationSubmitted,
    OfferAccepted,
    OfferDeclined,
)
from src.core.messaging.contracts.base import IntegrationMessage
from src.core.messaging.contracts.clients import (
    FinancialReportSubmitted,
    MemberAdded,
    MemberRemoved,
    MemberRoleChanged,
    OrganizationVerificationMismatch,
    OrganizationVerified,
)
from src.core.messaging.contracts.decision import (
    DecisionMade,
    ManualDecisionRejected,
    PreApprovedOffersUpdated,
)
from src.core.messaging.contracts.process import (
    ProcessFailed,
    StepCompleted,
    UserTaskCompleted,
    UserTaskCreated,
)
from src.modules.notifications.application.deliveries.applications import ApplicationDeliveries
from src.modules.notifications.application.deliveries.clients import ClientDeliveries
from src.modules.notifications.application.deliveries.context import DeliveryContext, Handlers
from src.modules.notifications.application.deliveries.decision import DecisionDeliveries
from src.modules.notifications.application.deliveries.process import ProcessDeliveries
from src.modules.notifications.application.interfaces.neighbours import Neighbours
from src.modules.notifications.application.interfaces.repositories import FeedStore
from src.modules.notifications.domain.feed import Delivery, task_group

HANDLED_MESSAGES: tuple[type[IntegrationMessage], ...] = (
    ApplicationSubmitted,
    ApplicationStatusChanged,
    ApplicationInfoProvided,
    OfferAccepted,
    OfferDeclined,
    ApplicationSigned,
    ApplicationCancelled,
    StepCompleted,
    UserTaskCreated,
    UserTaskCompleted,
    ProcessFailed,
    DecisionMade,
    ManualDecisionRejected,
    PreApprovedOffersUpdated,
    OrganizationVerified,
    OrganizationVerificationMismatch,
    MemberAdded,
    MemberRemoved,
    MemberRoleChanged,
    FinancialReportSubmitted,
)


def handled_types(topic: str) -> frozenset[str]:
    """Message types of the topic the feed reacts to (filter of the subscription)."""
    return frozenset(m.TYPE for m in HANDLED_MESSAGES if m.TOPIC == topic)


class ProjectEventUseCase:
    def __init__(self, store: FeedStore, neighbours: Neighbours) -> None:
        self._store = store
        ctx = DeliveryContext(neighbours)
        self._handlers: Handlers = {
            **ApplicationDeliveries(ctx).handlers(),
            **ProcessDeliveries(ctx).handlers(),
            **DecisionDeliveries(ctx).handlers(),
            **ClientDeliveries(ctx).handlers(),
        }

    async def execute(self, message: IntegrationMessage, event_id: UUID, now: datetime) -> int:
        """Write the feed records of one event; returns how many were written."""
        if isinstance(message, UserTaskCompleted):
            return await self._store.resolve_group(task_group(message.task_id), now)
        written = 0
        for delivery in await self.deliveries(message):
            if delivery.recipients:
                written += await self._store.append(delivery, event_id, message.TYPE, now)
        return written

    async def deliveries(self, message: IntegrationMessage) -> list[Delivery]:
        handler = self._handlers.get(type(message))
        return await handler(message) if handler is not None else []
