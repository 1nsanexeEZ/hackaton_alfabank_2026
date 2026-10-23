"""Notifications contract: feed counters and latest items for the dashboard."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

FeedItemType = Literal[
    "status_changed",
    "stage_changed",
    "info_requested",
    "offer_ready",
    "task_assigned",
    "advice",
    "news",
]


@dataclass(frozen=True, slots=True)
class FeedItemDTO:
    id: UUID
    type: FeedItemType
    title: str
    body: str
    link: str | None
    priority: Literal["low", "normal", "high"]
    action_required: bool
    organization_id: UUID | None
    application_id: UUID | None
    created_at: datetime
    read_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class NewsItemDTO:
    id: UUID
    title: str
    body: str
    published_at: datetime
    # Why the item was picked for this company ("ОКВЭД 56", "продукт OVERDRAFT").
    relevance: tuple[str, ...]


class NotificationsFacade(Protocol):
    async def unread_count(self, account_id: UUID, organization_id: UUID | None = None) -> int: ...

    async def latest(
        self,
        account_id: UUID,
        organization_id: UUID | None = None,
        application_id: UUID | None = None,
        limit: int = 10,
    ) -> list[FeedItemDTO]: ...

    async def personal_news(self, organization_id: UUID, limit: int = 5) -> list[NewsItemDTO]: ...
