from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.domain.clock import Clock
from src.core.facades import FacadeRegistry
from src.notifications.application.feed import BANK_ROLE_NAMES, viewer_recipients
from src.notifications.application.neighbours import Neighbours
from src.notifications.application.news import NewsService, to_dto
from src.notifications.application.ports import FeedFilter
from src.notifications.domain.feed import Recipient
from src.notifications.facade import FeedItemDTO, NewsItemDTO
from src.notifications.infrastructure.repositories import SqlAlchemyFeedStore, SqlAlchemyNewsStore


class NotificationsFacadeImpl:
    """Runs in the caller's session. Knows only the account id, so whether the
    account also reads the back office feed is asked from identity."""

    def __init__(self, session: AsyncSession, facades: FacadeRegistry, clock: Clock) -> None:
        self._feed = SqlAlchemyFeedStore(session)
        self._neighbours = Neighbours(lambda key: facades.get(key, session))
        self._news = NewsService(SqlAlchemyNewsStore(session), self._neighbours, clock)

    async def _recipients(self, account_id: UUID) -> tuple[Recipient, ...]:
        role = await self._neighbours.account_role(account_id)
        return viewer_recipients(account_id, bank_staff=role in BANK_ROLE_NAMES)

    async def unread_count(self, account_id: UUID, organization_id: UUID | None = None) -> int:
        return await self._feed.unread_count(
            await self._recipients(account_id), FeedFilter(organization_id=organization_id)
        )

    async def latest(
        self,
        account_id: UUID,
        organization_id: UUID | None = None,
        application_id: UUID | None = None,
        limit: int = 10,
    ) -> list[FeedItemDTO]:
        records, _ = await self._feed.page(
            await self._recipients(account_id),
            FeedFilter(organization_id=organization_id, application_id=application_id),
            limit=max(limit, 0),
            offset=0,
        )
        return [record.item for record in records]

    async def personal_news(self, organization_id: UUID, limit: int = 5) -> list[NewsItemDTO]:
        return [to_dto(ranked) for ranked in await self._news.personal(organization_id, limit)]
