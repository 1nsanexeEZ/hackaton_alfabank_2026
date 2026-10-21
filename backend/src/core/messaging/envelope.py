from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class Envelope(BaseModel):
    """What actually travels through Kafka: metadata + the contract payload."""

    model_config = ConfigDict(frozen=True)

    event_id: UUID
    type: str
    schema_version: int
    occurred_at: datetime
    producer: str
    # Id of the business entity the message is about (application, organization):
    # also the partition key.
    correlation_id: UUID
    # event_id of the message that caused this one (a reply to a command).
    causation_id: UUID | None = None
    payload: dict[str, Any]
