"""Stream tickets and events of the live feed (SSE)."""

from dataclasses import dataclass
from datetime import datetime

from src.modules.notifications.application.dto.feed import FeedRecordDTO
from src.modules.notifications.domain.enums import StreamEventName


@dataclass(frozen=True, slots=True)
class IssuedTicket:
    ticket: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class StreamEvent:
    event: StreamEventName
    id: str | None = None
    record: FeedRecordDTO | None = None
    at: datetime | None = None
