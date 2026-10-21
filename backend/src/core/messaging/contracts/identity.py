from uuid import UUID

from src.core.messaging import topics
from src.core.messaging.contracts.base import IntegrationMessage


class AccountRegistered(IntegrationMessage):
    TYPE = "AccountRegistered"
    TOPIC = topics.IDENTITY_EVENTS

    account_id: UUID
    role: str
