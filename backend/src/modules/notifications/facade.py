"""Notifications contract: feed counters and latest items for the dashboard.

The only entry point for other modules: the protocol below and the DTO it returns
(defined in `application/dto`, re-exported here)."""

from typing import Protocol
from uuid import UUID

from src.modules.notifications.application.dto.feed import FeedItemDTO
from src.modules.notifications.application.dto.news import NewsItemDTO
from src.modules.notifications.domain.enums import FeedItemType

__all__ = ["FeedItemDTO", "FeedItemType", "NewsItemDTO", "NotificationsFacade"]


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
