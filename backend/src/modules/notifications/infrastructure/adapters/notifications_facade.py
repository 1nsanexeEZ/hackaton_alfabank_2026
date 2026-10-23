"""`NotificationsFacade` for neighbours: only calls the use cases. Runs in the
caller's session; no access checks — the caller (bff) checks the company."""

from uuid import UUID

from src.modules.notifications.application.dto.feed import FeedItemDTO
from src.modules.notifications.application.dto.news import NewsItemDTO
from src.modules.notifications.application.use_cases.account_feed import (
    CountAccountUnreadUseCase,
    LatestAccountFeedUseCase,
)
from src.modules.notifications.application.use_cases.news import PersonalNewsUseCase
from src.modules.notifications.facade import NotificationsFacade


class NotificationsFacadeImpl(NotificationsFacade):
    def __init__(
        self,
        count_unread: CountAccountUnreadUseCase,
        latest: LatestAccountFeedUseCase,
        personal_news: PersonalNewsUseCase,
    ) -> None:
        self._count_unread = count_unread
        self._latest = latest
        self._personal_news = personal_news

    async def unread_count(self, account_id: UUID, organization_id: UUID | None = None) -> int:
        return await self._count_unread.execute(account_id, organization_id)

    async def latest(
        self,
        account_id: UUID,
        organization_id: UUID | None = None,
        application_id: UUID | None = None,
        limit: int = 10,
    ) -> list[FeedItemDTO]:
        return await self._latest.execute(account_id, organization_id, application_id, limit)

    async def personal_news(self, organization_id: UUID, limit: int = 5) -> list[NewsItemDTO]:
        return await self._personal_news.execute(organization_id, limit)
