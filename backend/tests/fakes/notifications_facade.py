from uuid import UUID

from src.modules.notifications.facade import FeedItemDTO, NewsItemDTO


class FakeNotificationsFacade:
    def __init__(self) -> None:
        self.items: dict[UUID, list[FeedItemDTO]] = {}
        self.news: dict[UUID, list[NewsItemDTO]] = {}

    def add_item(self, account_id: UUID, item: FeedItemDTO) -> FeedItemDTO:
        self.items.setdefault(account_id, []).append(item)
        return item

    def set_news(self, organization_id: UUID, news: list[NewsItemDTO]) -> None:
        self.news[organization_id] = news

    def _select(
        self, account_id: UUID, organization_id: UUID | None, application_id: UUID | None
    ) -> list[FeedItemDTO]:
        return [
            item
            for item in self.items.get(account_id, [])
            if (organization_id is None or item.organization_id == organization_id)
            and (application_id is None or item.application_id == application_id)
        ]

    async def unread_count(self, account_id: UUID, organization_id: UUID | None = None) -> int:
        return sum(
            1 for item in self._select(account_id, organization_id, None) if not item.read_at
        )

    async def latest(
        self,
        account_id: UUID,
        organization_id: UUID | None = None,
        application_id: UUID | None = None,
        limit: int = 10,
    ) -> list[FeedItemDTO]:
        items = self._select(account_id, organization_id, application_id)
        return sorted(items, key=lambda item: item.created_at, reverse=True)[:limit]

    async def personal_news(self, organization_id: UUID, limit: int = 5) -> list[NewsItemDTO]:
        return self.news.get(organization_id, [])[:limit]
