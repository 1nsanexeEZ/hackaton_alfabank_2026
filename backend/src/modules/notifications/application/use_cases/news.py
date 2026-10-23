"""Personal news of a company: its profile from clients, product interest from
applications and pre-approved offers, ranking in the domain."""

from uuid import UUID

from src.core.domain.clock import Clock
from src.core.exceptions.exceptions import NotFoundError
from src.core.uow import UnitOfWork
from src.modules.notifications.application.dto.news import NewsItemDTO, ViewerNewsDTO
from src.modules.notifications.application.interfaces.neighbours import Neighbours
from src.modules.notifications.application.interfaces.repositories import NewsStore
from src.modules.notifications.domain.news import CompanyProfile, RankedNews, rank_news

APPLIED = "есть заявка"
PRE_APPROVED = "предодобрен"


def news_dto(ranked: RankedNews) -> NewsItemDTO:
    article = ranked.article
    return NewsItemDTO(
        id=article.id,
        title=article.title,
        body=article.body,
        published_at=article.published_at,
        relevance=ranked.relevance,
    )


class PersonalNewsUseCase:
    def __init__(self, store: NewsStore, neighbours: Neighbours, clock: Clock) -> None:
        self._store = store
        self._neighbours = neighbours
        self._clock = clock

    async def execute(self, organization_id: UUID | None, limit: int) -> list[NewsItemDTO]:
        """Without a company — general news only."""
        profile = (
            CompanyProfile() if organization_id is None else await self._profile(organization_id)
        )
        articles = await self._store.published(self._clock.now())
        return [news_dto(ranked) for ranked in rank_news(articles, profile, limit)]

    async def _profile(self, organization_id: UUID) -> CompanyProfile:
        """Empty profile (general news only) when the company is unknown."""
        snapshot = await self._neighbours.organization(organization_id)
        if snapshot is None:
            return CompanyProfile()
        products: dict[str, str] = {}
        for code in await self._neighbours.application_products(organization_id):
            products.setdefault(code, APPLIED)
        for offer in await self._neighbours.pre_approved(organization_id):
            products.setdefault(offer.product_code, PRE_APPROVED)
        return CompanyProfile(
            okved_main=snapshot.okved_main,
            okved_extra=tuple(snapshot.okved_extra),
            legal_form=snapshot.legal_form,
            products=products,
        )


class ViewerNewsUseCase:
    """Personal news with the viewer's read marks (GET /news)."""

    def __init__(self, personal_news: PersonalNewsUseCase, store: NewsStore) -> None:
        self._personal_news = personal_news
        self._store = store

    async def execute(
        self, account_id: UUID, organization_id: UUID | None, limit: int
    ) -> list[ViewerNewsDTO]:
        news = await self._personal_news.execute(organization_id, limit)
        read = await self._store.read_ids(account_id, [item.id for item in news])
        return [ViewerNewsDTO(item, item.id in read) for item in news]


class MarkNewsReadUseCase:
    def __init__(self, store: NewsStore, uow: UnitOfWork, clock: Clock) -> None:
        self._store = store
        self._uow = uow
        self._clock = clock

    async def execute(self, news_id: UUID, account_id: UUID) -> None:
        async with self._uow:
            if not await self._store.exists(news_id):
                raise NotFoundError("News item not found")
            await self._store.mark_read(news_id, account_id, self._clock.now())
            await self._uow.commit()
