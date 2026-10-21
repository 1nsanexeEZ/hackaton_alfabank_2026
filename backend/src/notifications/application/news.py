"""Personal news of a company: its profile from clients, product interest from
applications and pre-approved offers, ranking in the domain."""

from uuid import UUID

from src.core.domain.clock import Clock
from src.core.exceptions.exceptions import NotFoundError
from src.core.uow import UnitOfWork
from src.notifications.application.neighbours import Neighbours
from src.notifications.application.ports import NewsStore
from src.notifications.domain.news import CompanyProfile, RankedNews, rank_news
from src.notifications.facade import NewsItemDTO

APPLIED = "есть заявка"
PRE_APPROVED = "предодобрен"


def to_dto(ranked: RankedNews) -> NewsItemDTO:
    article = ranked.article
    return NewsItemDTO(
        id=article.id,
        title=article.title,
        body=article.body,
        published_at=article.published_at,
        relevance=ranked.relevance,
    )


class NewsService:
    def __init__(
        self, store: NewsStore, neighbours: Neighbours, clock: Clock, uow: UnitOfWork | None = None
    ) -> None:
        self._store = store
        self._nb = neighbours
        self._clock = clock
        self._uow = uow

    async def profile(self, organization_id: UUID) -> CompanyProfile:
        """Empty profile (general news only) when the company is unknown."""
        snapshot = await self._nb.organization(organization_id)
        if snapshot is None:
            return CompanyProfile()
        products: dict[str, str] = {}
        for code in await self._nb.application_products(organization_id):
            products.setdefault(code, APPLIED)
        for offer in await self._nb.pre_approved(organization_id):
            products.setdefault(offer.product_code, PRE_APPROVED)
        return CompanyProfile(
            okved_main=snapshot.okved_main,
            okved_extra=tuple(snapshot.okved_extra),
            legal_form=snapshot.legal_form,
            products=products,
        )

    async def personal(self, organization_id: UUID | None, limit: int) -> list[RankedNews]:
        profile = (
            CompanyProfile() if organization_id is None else await self.profile(organization_id)
        )
        articles = await self._store.published(self._clock.now())
        return rank_news(articles, profile, limit)

    async def read_ids(self, account_id: UUID, news: list[RankedNews]) -> set[UUID]:
        return await self._store.read_ids(account_id, [r.article.id for r in news])

    async def mark_read(self, news_id: UUID, account_id: UUID) -> None:
        assert self._uow is not None, "mark_read needs a unit of work"
        async with self._uow:
            if not await self._store.exists(news_id):
                raise NotFoundError("News item not found")
            await self._store.mark_read(news_id, account_id, self._clock.now())
            await self._uow.commit()
