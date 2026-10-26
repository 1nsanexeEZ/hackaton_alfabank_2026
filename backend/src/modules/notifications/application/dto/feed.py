"""Feed records as the use cases return them, and the filter of a feed read."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from src.modules.notifications.domain.enums import Audience, FeedItemType, Priority


@dataclass(frozen=True, slots=True)
class FeedItemDTO:
    id: UUID
    type: FeedItemType
    title: str
    body: str
    link: str | None
    priority: Priority
    action_required: bool
    organization_id: UUID | None
    application_id: UUID | None
    created_at: datetime
    read_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class FeedRecordDTO:
    item: FeedItemDTO
    # Stream position: the SSE event id.
    seq: int
    audience: Audience


@dataclass(frozen=True, slots=True)
class FeedFilter:
    organization_id: UUID | None = None
    application_id: UUID | None = None
    unread_only: bool = False
    # A client's companies: records of any other company are hidden. None — no
    # limit (bank staff).
    organizations: frozenset[UUID] | None = None
