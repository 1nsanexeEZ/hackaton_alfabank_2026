from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.notifications.application.interfaces.repositories import NewsStore
from src.modules.notifications.domain.news import NewsArticle
from src.modules.notifications.infrastructure.database.models import NewsItem, NewsRead
from src.modules.notifications.infrastructure.repositories.mappers import to_article


class SqlAlchemyNewsStore(NewsStore):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def published(self, now: datetime) -> list[NewsArticle]:
        stmt = select(NewsItem).where(NewsItem.published_at <= now).order_by(NewsItem.slug)
        return [to_article(row) for row in (await self._session.scalars(stmt)).all()]

    async def exists(self, news_id: UUID) -> bool:
        return await self._session.get(NewsItem, news_id) is not None

    async def read_ids(self, account_id: UUID, news_ids: Sequence[UUID]) -> set[UUID]:
        if not news_ids:
            return set()
        stmt = select(NewsRead.news_id).where(
            NewsRead.account_id == account_id, NewsRead.news_id.in_(list(news_ids))
        )
        return set((await self._session.scalars(stmt)).all())

    async def mark_read(self, news_id: UUID, account_id: UUID, now: datetime) -> None:
        if await self._session.get(NewsRead, (news_id, account_id)) is None:
            self._session.add(NewsRead(news_id=news_id, account_id=account_id, read_at=now))
            await self._session.flush()

    async def upsert(self, article: NewsArticle, now: datetime) -> bool:
        """Seed: insert by slug or refresh the text and tags. True when inserted;
        the publication date of an existing article is kept."""
        row = (
            await self._session.scalars(select(NewsItem).where(NewsItem.slug == article.slug))
        ).one_or_none()
        inserted = row is None
        if row is None:
            row = NewsItem(
                id=article.id, slug=article.slug, published_at=article.published_at, created_at=now
            )
            self._session.add(row)
        row.title = article.title
        row.body = article.body
        row.okved_prefixes = list(article.okved_prefixes)
        row.product_codes = list(article.product_codes)
        row.legal_forms = list(article.legal_forms)
        row.is_general = article.is_general
        row.updated_at = now
        await self._session.flush()
        return inserted
