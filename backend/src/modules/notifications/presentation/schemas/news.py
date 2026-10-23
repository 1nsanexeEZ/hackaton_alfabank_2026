from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from src.modules.notifications.application.dto.news import ViewerNewsDTO


class NewsRead(BaseModel):
    id: UUID
    title: str
    body: str
    published_at: datetime
    # Why the article was picked for the company ("ОКВЭД 56 — общепит").
    relevance: list[str]
    read: bool

    @classmethod
    def from_dto(cls, viewer_news: ViewerNewsDTO) -> "NewsRead":
        news = viewer_news.news
        return cls(
            id=news.id,
            title=news.title,
            body=news.body,
            published_at=news.published_at,
            relevance=list(news.relevance),
            read=viewer_news.read,
        )
